from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wrapper.server import (
    MAX_MULTIPART_OVERHEAD_BYTES,
    MAX_UPLOAD_BYTES,
    MXL_MEDIA_TYPE,
    app,
)


@pytest.fixture
def fake_audiveris(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake = Path(__file__).with_name("fake_audiveris.py")
    fake.chmod(0o755)
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUDIVERIS_COMMAND", str(fake))
    monkeypatch.setenv("FAKE_AUDIVERIS_TRACE", str(trace))
    monkeypatch.delenv("FAKE_AUDIVERIS_MODE", raising=False)
    monkeypatch.setenv("OMR_TRANSCRIBE_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("OMR_PROCESS_TERM_GRACE_SECONDS", "0.1")
    return trace


def post_png(client: TestClient, name: str = "score.png"):
    return client.post(
        "/transcribe",
        files={"file": (name, b"\x89PNG\r\n\x1a\nscore", "image/png")},
    )


def test_healthz() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_transcribe_returns_valid_mxl_and_cleans_workspace(fake_audiveris: Path) -> None:
    with TestClient(app) as client:
        response = post_png(client, "../../unsafe.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == MXL_MEDIA_TYPE
    assert response.headers["content-disposition"] == 'attachment; filename="transcription.mxl"'
    assert response.content.startswith(b"PK")

    invocation = json.loads(fake_audiveris.read_text(encoding="utf-8"))
    input_path = Path(invocation["input"])
    output_path = Path(invocation["output"])
    assert input_path.name == "input.png"
    assert not input_path.exists()
    assert not output_path.exists()
    assert invocation["args"][:4] == ["-batch", "-export", "-output", str(output_path)]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("score.pdf", b"%PDF-1.7\nscore"),
        ("score.jpg", b"\xff\xd8\xffscore"),
        ("score.jpeg", b"\xff\xd8\xffscore"),
    ],
)
def test_accepts_each_supported_format(fake_audiveris: Path, name: str, content: bytes) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": (name, content, "application/octet-stream")},
        )
    assert response.status_code == 200


def test_accepts_exactly_25_mib(fake_audiveris: Path) -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (MAX_UPLOAD_BYTES - 8)
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("large.png", content, "image/png")},
        )
    assert response.status_code == 200


@pytest.mark.parametrize("name", ["score.gif", "score", "score.png.exe"])
def test_rejects_unsupported_filename(fake_audiveris: Path, name: str) -> None:
    with TestClient(app) as client:
        response = post_png(client, name)
    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_FILE",
            "message": "The uploaded file is not a supported PDF or image.",
        }
    }


def test_rejects_spoofed_file(fake_audiveris: Path) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("score.pdf", b"not a pdf", "application/pdf")},
        )
    assert response.status_code == 415
    assert not fake_audiveris.exists()


def test_rejects_more_than_25_mib(fake_audiveris: Path) -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (MAX_UPLOAD_BYTES - 7)
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("large.png", content, "image/png")},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_stops_oversized_chunked_body_while_streaming(fake_audiveris: Path) -> None:
    boundary = "chunked-boundary"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()
    remaining = MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES + 1

    def chunks():
        nonlocal remaining
        yield prefix
        first = b"\x89PNG\r\n\x1a\n"
        yield first
        remaining -= len(first)
        block = b"x" * (1024 * 1024)
        while remaining:
            chunk = block[:remaining]
            remaining -= len(chunk)
            yield chunk
        yield suffix

    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            content=chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert not fake_audiveris.exists()


@pytest.mark.parametrize(
    ("files", "expected_code"),
    [
        (None, "INVALID_CONTENT_TYPE"),
        ({"other": ("score.png", b"\x89PNG\r\n\x1a\n", "image/png")}, "INVALID_FILE_COUNT"),
        (
            [
                ("file", ("one.png", b"\x89PNG\r\n\x1a\n", "image/png")),
                ("file", ("two.png", b"\x89PNG\r\n\x1a\n", "image/png")),
            ],
            "INVALID_FILE_COUNT",
        ),
    ],
)
def test_requires_exactly_one_file(fake_audiveris: Path, files, expected_code: str) -> None:
    with TestClient(app) as client:
        response = client.post("/transcribe", files=files)
    assert response.status_code in {400, 415}
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.parametrize("mode", ["fail", "missing", "invalid", "multiple"])
def test_returns_safe_fixed_error_for_bad_output(
    fake_audiveris: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.setenv("FAKE_AUDIVERIS_MODE", mode)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post_png(client)
    assert response.status_code == 502
    assert set(response.json()) == {"error"}
    assert "private fake failure details" not in response.text


def test_timeout_kills_the_process_group(
    fake_audiveris: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "pid"
    monkeypatch.setenv("FAKE_AUDIVERIS_MODE", "hang")
    monkeypatch.setenv("FAKE_AUDIVERIS_PID", str(pid_file))
    monkeypatch.setenv("OMR_TRANSCRIBE_TIMEOUT_SECONDS", "0.1")
    with TestClient(app) as client:
        response = post_png(client)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "TRANSCRIPTION_TIMEOUT"
    pid = int(pid_file.read_text(encoding="ascii"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_audiveris_executions_are_serialized(
    fake_audiveris: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FAKE_AUDIVERIS_MODE", "guard")
    monkeypatch.setenv("FAKE_AUDIVERIS_GUARD", str(tmp_path / "audiveris.lock"))
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: post_png(client), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
