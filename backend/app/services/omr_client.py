"""Audiveris OMR ラッパへの小さな非同期 HTTP クライアント。"""

from __future__ import annotations

import io
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx

from app import config

MAX_MXL_BYTES = 50 * 1024 * 1024
MXL_BUNDLE_MEDIA_TYPE = "application/zip"


class OmrUnavailableError(Exception):
    """OMR サービスへ接続できない、または health check が不正。"""


class OmrTranscriptionError(Exception):
    """OMR サービスは応答したが、変換に失敗した。"""


class OmrClient:
    """接続先を呼び出し時に解決し、テストでは HTTP client を注入できる。"""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    def _url(self, path: str) -> str:
        base_url = str(config.OMR_SERVICE_URL).rstrip("/")
        if not base_url:
            raise OmrUnavailableError("OMR service URL is empty")
        return f"{base_url}{path}"

    @asynccontextmanager
    async def _client(self, timeout: float) -> AsyncIterator[httpx.AsyncClient]:
        if self._http_client is not None:
            yield self._http_client
            return
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            yield client

    async def ensure_available(self) -> None:
        """profile 無効などをジョブ作成前に検出する。"""
        try:
            async with self._client(config.OMR_HEALTHCHECK_TIMEOUT_SECONDS) as client:
                response = await client.get(self._url("/healthz"))
        except (httpx.HTTPError, ValueError) as exc:
            raise OmrUnavailableError("OMR health check failed") from exc

        if response.status_code != 200:
            raise OmrUnavailableError("OMR health check returned a non-200 response")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OmrUnavailableError("OMR health check returned invalid JSON") from exc
        if payload != {"status": "ok"}:
            raise OmrUnavailableError("OMR health check returned an unexpected payload")

    async def transcribe(self, input_path: Path, source_filename: str) -> list[bytes]:
        """入力を multipart で送信し、サイズ制限内の MXL を返す。
        Audiverisが複数ページと誤認識した場合は、ZIPで束ねられた複数件が
        返るため、その場合はすべて展開して返す(通常は要素数1のリスト)。
        """
        try:
            with input_path.open("rb") as input_file:
                async with self._client(config.OMR_REQUEST_TIMEOUT_SECONDS) as client:
                    async with client.stream(
                        "POST",
                        self._url("/transcribe"),
                        files={
                            "file": (
                                source_filename,
                                input_file,
                                "application/octet-stream",
                            )
                        },
                    ) as response:
                        if response.status_code != 200:
                            raise OmrTranscriptionError(
                                f"OMR returned HTTP {response.status_code}"
                            )
                        content_type = (
                            response.headers.get("content-type", "")
                            .partition(";")[0]
                            .strip()
                            .lower()
                        )
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_MXL_BYTES:
                                raise OmrTranscriptionError("OMR response is too large")
        except OmrTranscriptionError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise OmrUnavailableError("OMR request failed") from exc

        if not content:
            raise OmrTranscriptionError("OMR returned an empty response")

        if content_type == MXL_BUNDLE_MEDIA_TYPE:
            try:
                with zipfile.ZipFile(io.BytesIO(bytes(content))) as archive:
                    names = sorted(archive.namelist())
                    if not names:
                        raise OmrTranscriptionError("OMR returned an empty page bundle")
                    return [archive.read(name) for name in names]
            except zipfile.BadZipFile as exc:
                raise OmrTranscriptionError("OMR returned an invalid page bundle") from exc

        return [bytes(content)]
