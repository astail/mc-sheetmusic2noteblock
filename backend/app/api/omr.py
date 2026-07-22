"""PDF・画像を既存 score パイプラインへ合流させる非同期 OMR API。"""

from __future__ import annotations

import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, UploadFile, status

from app import storage
from app.models.omr import OmrJobCreated, OmrJobError, OmrJobRecord, OmrJobResponse
from app.services.omr_client import (
    OmrClient,
    OmrTranscriptionError,
    OmrUnavailableError,
)
from app.services.parser import parse_score

router = APIRouter(prefix="/omr", tags=["omr"])

OMR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024

_tasks: dict[str, asyncio.Task[None]] = {}
_worker_lock: asyncio.Lock | None = None
_worker_loop: asyncio.AbstractEventLoop | None = None

INTERRUPTED_ERROR = OmrJobError(
    code="OMR_INTERRUPTED",
    message="サーバー再起動によりOMR処理が中断されました。再度アップロードしてください。",
)


def get_omr_client() -> OmrClient:
    return OmrClient()


def _job_response(record: OmrJobRecord) -> OmrJobResponse:
    return OmrJobResponse(
        job_id=record.job_id,
        status=record.status,
        score_id=record.score_id,
        error=record.error,
    )


def _current_worker_lock() -> asyncio.Lock:
    global _worker_lock, _worker_loop
    loop = asyncio.get_running_loop()
    if _worker_lock is None or _worker_loop is not loop:
        _worker_lock = asyncio.Lock()
        _worker_loop = loop
    return _worker_lock


async def _read_upload(file: UploadFile) -> bytes:
    content = bytearray()
    while chunk := await file.read(COPY_CHUNK_BYTES):
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="OMR入力は25MiB以下にしてください",
            )
    if not content:
        raise HTTPException(status_code=422, detail="空のファイルは処理できません")
    return bytes(content)


def _register_score(source_filename: str, mxl_content: bytes) -> str:
    output_name = f"{Path(source_filename).stem or 'transcription'}.mxl"
    score_id = storage.create_score(output_name, mxl_content)
    try:
        original = storage.original_path(score_id)
        if original is None:
            raise ValueError("保存したMXLが見つかりません")
        parsed = parse_score(original)
        storage.save_parsed(score_id, parsed.summary)
    except BaseException:
        shutil.rmtree(storage.score_dir(score_id), ignore_errors=True)
        raise
    return score_id


async def _register_score_shielded(source_filename: str, mxl_content: bytes) -> str:
    """_register_score をスレッドプールで実行する。呼び出し元がキャンセルされてもスレッド自体は
    完了まで走り続けるため、キャンセル時は完了を待ってから孤立スコアを後始末する。"""
    task = asyncio.ensure_future(
        asyncio.to_thread(_register_score, source_filename, mxl_content)
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            orphan_score_id = await task
        except Exception:
            pass
        else:
            shutil.rmtree(storage.score_dir(orphan_score_id), ignore_errors=True)
        raise


async def _finalize_job_done(job_id: str, score_id: str) -> None:
    """ジョブを done として確定する。呼び出し元がキャンセルされてもこの更新自体は
    完了まで走らせ、確定済みの done を後から failed で上書きしないようにする。"""
    task = asyncio.ensure_future(
        asyncio.to_thread(storage.update_omr_job, job_id, "done", score_id=score_id)
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task


async def _fail_job(job_id: str, error: OmrJobError) -> None:
    try:
        previous = await asyncio.to_thread(storage.load_omr_job, job_id)
        await asyncio.to_thread(storage.update_omr_job, job_id, "failed", error=error)
    except (OSError, storage.OmrJobDataError, ValueError):
        # 永続ストレージ自体が壊れている場合は task の例外を外へ漏らさない。
        return
    if previous is not None and previous.score_id is not None:
        # done 確定前に score だけ登録が完了していた場合、失敗確定時に孤立を残さない。
        shutil.rmtree(storage.score_dir(previous.score_id), ignore_errors=True)


async def _run_job(job_id: str, client: OmrClient) -> None:
    try:
        async with _current_worker_lock():
            record = await asyncio.to_thread(storage.load_omr_job, job_id)
            if record is None:
                return
            await asyncio.to_thread(storage.update_omr_job, job_id, "running")
            input_path = storage.omr_job_input_path(job_id, record.source_filename)
            mxl_content = await client.transcribe(input_path, record.source_filename)
            score_id = await _register_score_shielded(
                record.source_filename, mxl_content
            )
            await asyncio.to_thread(
                storage.update_omr_job, job_id, "running", score_id=score_id
            )
            try:
                await _finalize_job_done(job_id, score_id)
            except BaseException:
                shutil.rmtree(storage.score_dir(score_id), ignore_errors=True)
                raise
    except asyncio.CancelledError:
        await _fail_job(job_id, INTERRUPTED_ERROR)
        raise
    except OmrUnavailableError:
        await _fail_job(
            job_id,
            OmrJobError(
                code="OMR_UNAVAILABLE",
                message="OMRサービスに接続できませんでした。OMR profileの起動状態を確認してください。",
            ),
        )
    except OmrTranscriptionError:
        await _fail_job(
            job_id,
            OmrJobError(
                code="OMR_FAILED",
                message="楽譜画像を認識できませんでした。入力品質や形式を確認してください。",
            ),
        )
    except Exception:
        await _fail_job(
            job_id,
            OmrJobError(
                code="OMR_PROCESSING_FAILED",
                message="OMR結果を楽譜として登録できませんでした。",
            ),
        )
    finally:
        try:
            await asyncio.to_thread(storage.cleanup_omr_job_input, job_id)
        except (OSError, ValueError):
            pass


def _task_done(job_id: str, task: asyncio.Task[None]) -> None:
    _tasks.pop(job_id, None)
    if not task.cancelled():
        task.exception()  # 予期しない task 例外の warning を回収する


def _schedule_job(job_id: str, client: OmrClient) -> None:
    task = asyncio.create_task(_run_job(job_id, client), name=f"omr-job-{job_id}")
    _tasks[job_id] = task
    task.add_done_callback(lambda completed: _task_done(job_id, completed))


async def recover_interrupted_jobs() -> None:
    """前プロセスで queued/running だったジョブを明示的な失敗へ遷移する。"""
    records = await asyncio.to_thread(storage.iter_omr_jobs)
    for record in records:
        if record.status in {"queued", "running"} and record.job_id not in _tasks:
            await _fail_job(record.job_id, INTERRUPTED_ERROR)
            await asyncio.to_thread(storage.cleanup_omr_job_input, record.job_id)


async def cancel_active_jobs() -> None:
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await recover_interrupted_jobs()
    try:
        yield
    finally:
        await cancel_active_jobs()


@router.post(
    "/jobs",
    response_model=OmrJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job(
    file: UploadFile,
    client: OmrClient = Depends(get_omr_client),
) -> OmrJobCreated:
    source_filename = Path(file.filename or "").name
    extension = Path(source_filename).suffix.lower()
    if extension not in OMR_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="OMRは .pdf / .png / .jpg / .jpeg のみ対応しています",
        )

    try:
        await client.ensure_available()
    except OmrUnavailableError as exc:
        raise HTTPException(
            status_code=501,
            detail="OMRサービスが無効です。docker compose --profile omr up で起動してください。",
        ) from exc

    content = await _read_upload(file)
    try:
        record = await asyncio.to_thread(
            storage.create_omr_job, source_filename, content
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="OMRジョブを保存できませんでした",
        ) from exc
    _schedule_job(record.job_id, client)
    return OmrJobCreated(job_id=record.job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=OmrJobResponse)
async def get_job(job_id: str) -> OmrJobResponse:
    try:
        record = await asyncio.to_thread(storage.load_omr_job, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="OMRジョブが見つかりません") from exc
    except storage.OmrJobDataError as exc:
        raise HTTPException(
            status_code=500,
            detail="OMRジョブの状態を読み取れません",
        ) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="OMRジョブが見つかりません")
    if record.status in {"queued", "running"} and job_id not in _tasks:
        await _fail_job(job_id, INTERRUPTED_ERROR)
        await asyncio.to_thread(storage.cleanup_omr_job_input, job_id)
        record = await asyncio.to_thread(storage.load_omr_job, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="OMRジョブが見つかりません")
    return _job_response(record)
