"""OMR HTTP client の接続失敗・応答境界を検証する。"""

import asyncio
import io
import zipfile
from pathlib import Path

import httpx
import pytest

from app import config
from app.services import omr_client
from app.services.omr_client import (
    OmrClient,
    OmrTranscriptionError,
    OmrUnavailableError,
)


def _run(coro):
    return asyncio.run(coro)


def test_healthcheck_accepts_wrapper_health(monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test:8080")

    async def scenario():
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == httpx.URL("http://omr.test:8080/healthz")
            return httpx.Response(200, json={"status": "ok"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await OmrClient(http).ensure_available()

    _run(scenario())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"status": "starting"}),
    ],
)
def test_healthcheck_rejects_unhealthy_response(monkeypatch, response):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")

    async def scenario():
        async def handler(_: httpx.Request) -> httpx.Response:
            return response

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(OmrUnavailableError):
                await OmrClient(http).ensure_available()

    _run(scenario())


def test_healthcheck_maps_connection_failure_to_unavailable(monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")

    async def scenario():
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private host detail", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(OmrUnavailableError) as error:
                await OmrClient(http).ensure_available()
            assert "private host detail" not in str(error.value)

    _run(scenario())


def test_transcribe_posts_multipart_and_returns_mxl(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")
    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-test")

    async def scenario():
        async def handler(request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            assert request.url.path == "/transcribe"
            assert b'name="file"; filename="score.pdf"' in body
            assert b"%PDF-test" in body
            return httpx.Response(200, content=b"mxl-data")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await OmrClient(http).transcribe(source, "score.pdf")

    assert _run(scenario()) == [b"mxl-data"]


def test_transcribe_unpacks_multi_page_zip_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")
    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-test")

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("page_0.mxl", b"page-0-data")
        archive.writestr("page_1.mxl", b"page-1-data")

    async def scenario():
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=bundle.getvalue(),
                headers={"content-type": omr_client.MXL_BUNDLE_MEDIA_TYPE},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await OmrClient(http).transcribe(source, "score.pdf")

    assert _run(scenario()) == [b"page-0-data", b"page-1-data"]


def test_transcribe_rejects_invalid_zip_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")
    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-test")

    async def scenario():
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"not a real zip",
                headers={"content-type": omr_client.MXL_BUNDLE_MEDIA_TYPE},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(OmrTranscriptionError):
                await OmrClient(http).transcribe(source, "score.pdf")

    _run(scenario())


def test_transcribe_rejects_remote_failure_without_echoing_body(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")
    source = tmp_path / "input.png"
    source.write_bytes(b"png")

    async def scenario():
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(422, text="sensitive Audiveris stderr")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(OmrTranscriptionError) as error:
                await OmrClient(http).transcribe(source, "score.png")
            assert "sensitive" not in str(error.value)

    _run(scenario())


def test_transcribe_limits_response_size(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OMR_SERVICE_URL", "http://omr.test")
    monkeypatch.setattr(omr_client, "MAX_MXL_BYTES", 3)
    source = tmp_path / "input.jpg"
    source.write_bytes(b"jpeg")

    async def scenario():
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"four")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(OmrTranscriptionError):
                await OmrClient(http).transcribe(source, "score.jpg")

    _run(scenario())
