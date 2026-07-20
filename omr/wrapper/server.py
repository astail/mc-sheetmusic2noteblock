"""Small, defensive HTTP boundary around the Audiveris batch command."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import shutil
import signal
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from xml.etree import ElementTree
import zipfile

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

LOGGER = logging.getLogger("omr.wrapper")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
COPY_CHUNK_BYTES = 1024 * 1024
MXL_MEDIA_TYPE = "application/vnd.recordare.musicxml+xml"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAGIC_BYTES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str


class _RequestTooLarge(MultiPartException):
    pass


class AudiverisRunner:
    """Admit one Audiveris invocation and own its process group."""

    def __init__(self) -> None:
        self._state_lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._accepting = True
        self._busy = False

    async def start(self) -> None:
        async with self._state_lock:
            self._accepting = True
            self._busy = False

    async def admit(self) -> None:
        """Atomically reserve the sole execution slot without queueing."""
        async with self._state_lock:
            if not self._accepting:
                raise ApiError(503, "SERVICE_UNAVAILABLE", "The OMR service is shutting down.")
            if self._busy:
                raise ApiError(503, "SERVICE_BUSY", "The OMR service is busy.")
            self._busy = True

    async def release(self) -> None:
        async with self._state_lock:
            self._busy = False

    async def stop(self) -> None:
        async with self._state_lock:
            self._accepting = False
            process = self._process
        if process is not None:
            await _terminate_process_group(process)

    async def run(self, input_path: Path, output_dir: Path, log_path: Path) -> None:
        with log_path.open("wb") as log_file:
            async with self._state_lock:
                if not self._accepting:
                    raise ApiError(503, "SERVICE_UNAVAILABLE", "The OMR service is shutting down.")
                if not self._busy:
                    raise RuntimeError("Audiveris execution was not admitted")

                command = os.environ.get("AUDIVERIS_COMMAND", "Audiveris")
                if not command or "\x00" in command:
                    raise RuntimeError("AUDIVERIS_COMMAND is invalid")
                timeout = _positive_float_env("OMR_TRANSCRIBE_TIMEOUT_SECONDS", 300.0)
                try:
                    process = await asyncio.create_subprocess_exec(
                        command,
                        "-batch",
                        "-export",
                        "-output",
                        str(output_dir),
                        "--",
                        str(input_path),
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=asyncio.subprocess.STDOUT,
                        start_new_session=True,
                    )
                except OSError as exc:
                    LOGGER.exception("Unable to start Audiveris")
                    raise ApiError(
                        502,
                        "TRANSCRIPTION_FAILED",
                        "The score could not be transcribed.",
                    ) from exc
                self._process = process
            try:
                return_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            except TimeoutError as exc:
                await _terminate_process_group(process)
                raise ApiError(
                    504,
                    "TRANSCRIPTION_TIMEOUT",
                    "The transcription timed out.",
                ) from exc
            except asyncio.CancelledError:
                await _terminate_process_group(process)
                raise
            finally:
                async with self._state_lock:
                    if self._process is process:
                        self._process = None

        if return_code != 0:
            LOGGER.error("Audiveris exited with status %d", return_code)
            raise ApiError(
                502,
                "TRANSCRIPTION_FAILED",
                "The score could not be transcribed.",
            )


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


async def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    grace = _positive_float_env("OMR_PROCESS_TERM_GRACE_SECONDS", 2.0)
    try:
        await asyncio.wait_for(process.wait(), timeout=grace)
        return
    except TimeoutError:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


def _json_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def _one_upload(request: Request) -> UploadFile:
    content_type = request.headers.get("content-type", "")
    if content_type.partition(";")[0].strip().lower() != "multipart/form-data":
        raise ApiError(415, "INVALID_CONTENT_TYPE", "Content-Type must be multipart/form-data.")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise ApiError(400, "INVALID_MULTIPART", "The multipart request is invalid.") from exc
        if declared_length < 0:
            raise ApiError(400, "INVALID_MULTIPART", "The multipart request is invalid.")
        if declared_length > MAX_REQUEST_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "The uploaded file exceeds 25 MiB.")

    parser = MultiPartParser(
        headers=request.headers,
        stream=_limited_request_stream(request.stream()),
        max_files=2,
        max_fields=1,
    )
    try:
        form = await parser.parse()
    except _RequestTooLarge as exc:
        raise ApiError(413, "FILE_TOO_LARGE", "The uploaded file exceeds 25 MiB.") from exc
    except MultiPartException as exc:
        raise ApiError(400, "INVALID_MULTIPART", "The multipart request is invalid.") from exc
    except Exception as exc:
        raise ApiError(400, "INVALID_MULTIPART", "The multipart request is invalid.") from exc

    items = form.multi_items()
    uploads = [(key, value) for key, value in items if isinstance(value, StarletteUploadFile)]
    if len(uploads) != 1 or uploads[0][0] != "file" or len(items) != 1:
        for _, upload in uploads:
            await upload.close()
        raise ApiError(400, "INVALID_FILE_COUNT", "Exactly one file field named 'file' is required.")
    return uploads[0][1]


async def _limited_request_stream(stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    received = 0
    async for chunk in stream:
        received += len(chunk)
        if received > MAX_REQUEST_BYTES:
            raise _RequestTooLarge("multipart body too large")
        yield chunk


async def _store_upload(upload: UploadFile, destination: Path, extension: str) -> None:
    total = 0
    signature = b""
    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(COPY_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise ApiError(413, "FILE_TOO_LARGE", "The uploaded file exceeds 25 MiB.")
                if len(signature) < 8:
                    signature = (signature + chunk)[:8]
                output.write(chunk)
    finally:
        await upload.close()

    if total == 0:
        raise ApiError(400, "EMPTY_FILE", "The uploaded file is empty.")
    if not any(signature.startswith(prefix) for prefix in MAGIC_BYTES[extension]):
        raise ApiError(415, "UNSUPPORTED_FILE", "The uploaded file is not a supported PDF or image.")


def _find_valid_mxl(output_dir: Path) -> Path:
    candidates = [
        path
        for path in output_dir.rglob("*")
        if path.suffix.lower() == ".mxl" and path.is_file() and not path.is_symlink()
    ]
    if len(candidates) != 1:
        raise ApiError(502, "INVALID_TRANSCRIPTION_OUTPUT", "The transcription output is invalid.")

    mxl_path = candidates[0]
    try:
        mxl_path.resolve(strict=True).relative_to(output_dir.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ApiError(502, "INVALID_TRANSCRIPTION_OUTPUT", "The transcription output is invalid.") from exc
    try:
        with zipfile.ZipFile(mxl_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("duplicate ZIP member")
            if archive.testzip() is not None:
                raise ValueError("corrupt ZIP member")
            container_info = archive.getinfo("META-INF/container.xml")
            if container_info.file_size > 64 * 1024:
                raise ValueError("oversized MXL container")
            container_data = archive.read("META-INF/container.xml")
            container = ElementTree.fromstring(container_data)
            rootfiles = [
                element.attrib.get("full-path", "")
                for element in container.iter()
                if element.tag.rsplit("}", 1)[-1] == "rootfile"
            ]
            if len(rootfiles) != 1 or rootfiles[0] not in names:
                raise ValueError("invalid MXL rootfile")
    except (OSError, ElementTree.ParseError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        LOGGER.warning("Audiveris produced an invalid MXL: %s", exc)
        raise ApiError(
            502,
            "INVALID_TRANSCRIPTION_OUTPUT",
            "The transcription output is invalid.",
        ) from exc
    return mxl_path


runner = AudiverisRunner()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runner.start()
    yield
    await runner.stop()


app = FastAPI(title="Audiveris OMR wrapper", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return _json_error(exc.status_code, exc.code, exc.message)


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled OMR wrapper error", exc_info=exc)
    return _json_error(500, "INTERNAL_ERROR", "An internal error occurred.")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcribe", response_class=FileResponse)
async def transcribe(request: Request) -> FileResponse:
    await runner.admit()
    try:
        upload = await _one_upload(request)
        extension = Path(upload.filename or "").suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            await upload.close()
            raise ApiError(415, "UNSUPPORTED_FILE", "The uploaded file is not a supported PDF or image.")

        work_dir = Path(tempfile.mkdtemp(prefix="omr-request-", dir=os.environ.get("TMPDIR")))
        try:
            input_path = work_dir / f"input{extension}"
            output_dir = work_dir / "output"
            output_dir.mkdir()
            await _store_upload(upload, input_path, extension)
            await runner.run(input_path, output_dir, work_dir / "audiveris.log")
            mxl_path = _find_valid_mxl(output_dir)
            return FileResponse(
                mxl_path,
                media_type=MXL_MEDIA_TYPE,
                filename="transcription.mxl",
                background=BackgroundTask(shutil.rmtree, work_dir, True),
            )
        except BaseException:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
    finally:
        await runner.release()
