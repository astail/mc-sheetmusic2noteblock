from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import time
import zipfile
import io

import fitz
import pytest
from fastapi.testclient import TestClient

import wrapper.server as server
from wrapper.server import (
    MAX_MULTIPART_OVERHEAD_BYTES,
    MAX_UPLOAD_BYTES,
    MXL_BUNDLE_MEDIA_TYPE,
    MXL_MEDIA_TYPE,
    app,
)


def _make_pdf(num_pages: int) -> bytes:
    with fitz.open() as document:
        for _ in range(num_pages):
            document.new_page(width=595, height=842)
        return document.tobytes()


@pytest.fixture
def fake_homr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake = Path(__file__).with_name("fake_homr.py")
    fake.chmod(0o755)
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("HOMR_COMMAND", str(fake))
    monkeypatch.setenv("FAKE_HOMR_TRACE", str(trace))
    monkeypatch.delenv("FAKE_HOMR_MODE", raising=False)
    monkeypatch.setenv("OMR_TRANSCRIBE_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("OMR_PROCESS_TERM_GRACE_SECONDS", "0.1")
    return trace


def post_png(client: TestClient, name: str = "score.png"):
    return client.post(
        "/transcribe",
        files={"file": (name, b"\x89PNG\r\n\x1a\nscore", "image/png")},
    )


def post_pdf(client: TestClient, content: bytes, name: str = "score.pdf"):
    return client.post(
        "/transcribe",
        files={"file": (name, content, "application/pdf")},
    )


def test_healthz() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_transcribe_image_returns_valid_mxl_and_cleans_workspace(fake_homr: Path) -> None:
    with TestClient(app) as client:
        response = post_png(client, "../../unsafe.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == MXL_MEDIA_TYPE
    assert response.headers["content-disposition"] == 'attachment; filename="transcription.mxl"'
    assert response.content.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"META-INF/container.xml", "score.musicxml"}

    invocation = json.loads(fake_homr.read_text(encoding="utf-8"))
    image_path = Path(invocation["image"])
    assert image_path.name == "input.png"
    assert not image_path.exists()  # work_dir はレスポンス送出後に削除される


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("score.jpg", b"\xff\xd8\xffscore"),
        ("score.jpeg", b"\xff\xd8\xffscore"),
    ],
)
def test_accepts_each_supported_image_format(fake_homr: Path, name: str, content: bytes) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": (name, content, "application/octet-stream")},
        )
    assert response.status_code == 200


def test_single_page_pdf_returns_a_single_mxl_not_a_bundle(fake_homr: Path) -> None:
    with TestClient(app) as client:
        response = post_pdf(client, _make_pdf(1))
    assert response.status_code == 200
    assert response.headers["content-type"] == MXL_MEDIA_TYPE

    invocations = [json.loads(line) for line in fake_homr.read_text(encoding="utf-8").splitlines()]
    assert len(invocations) == 1
    assert Path(invocations[0]["image"]).name == "page_0.png"


def test_multi_page_pdf_is_rasterized_and_bundled_as_zip(fake_homr: Path) -> None:
    with TestClient(app) as client:
        response = post_pdf(client, _make_pdf(3))
    assert response.status_code == 200
    assert response.headers["content-type"] == MXL_BUNDLE_MEDIA_TYPE
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="transcription-bundle.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert sorted(bundle.namelist()) == ["page_0.mxl", "page_1.mxl", "page_2.mxl"]
        for name in bundle.namelist():
            assert bundle.read(name).startswith(b"PK")

    # homr が各ページごとに1回ずつ、正しい画像で呼び出されたこと
    invocations = [json.loads(line) for line in fake_homr.read_text(encoding="utf-8").splitlines()]
    assert len(invocations) == 3
    assert sorted(Path(inv["image"]).name for inv in invocations) == [
        "page_0.png",
        "page_1.png",
        "page_2.png",
    ]


def test_rejects_corrupt_pdf(fake_homr: Path) -> None:
    with TestClient(app) as client:
        response = post_pdf(client, b"%PDF-1.7\nnot a real pdf")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_accepts_exactly_25_mib(fake_homr: Path) -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (MAX_UPLOAD_BYTES - 8)
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("large.png", content, "image/png")},
        )
    assert response.status_code == 200


@pytest.mark.parametrize("name", ["score.gif", "score", "score.png.exe"])
def test_rejects_unsupported_filename(fake_homr: Path, name: str) -> None:
    with TestClient(app) as client:
        response = post_png(client, name)
    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_FILE",
            "message": "The uploaded file is not a supported PDF or image.",
        }
    }


def test_rejects_spoofed_file(fake_homr: Path) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("score.pdf", b"not a pdf", "application/pdf")},
        )
    assert response.status_code == 415
    assert not fake_homr.exists()


def test_rejects_more_than_25_mib(fake_homr: Path) -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (MAX_UPLOAD_BYTES - 7)
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("large.png", content, "image/png")},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


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
def test_requires_exactly_one_file(fake_homr: Path, files, expected_code: str) -> None:
    with TestClient(app) as client:
        response = client.post("/transcribe", files=files)
    assert response.status_code in {400, 415}
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.parametrize("mode", ["fail", "missing", "empty"])
def test_returns_safe_fixed_error_for_bad_output(
    fake_homr: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.setenv("FAKE_HOMR_MODE", mode)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post_png(client)
    assert response.status_code == 502
    assert set(response.json()) == {"error"}
    assert "private fake failure details" not in response.text


def test_timeout_kills_the_process_group(
    fake_homr: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "pid"
    monkeypatch.setenv("FAKE_HOMR_MODE", "hang")
    monkeypatch.setenv("FAKE_HOMR_PID", str(pid_file))
    monkeypatch.setenv("OMR_TRANSCRIBE_TIMEOUT_SECONDS", "0.1")
    with TestClient(app) as client:
        response = post_png(client)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "TRANSCRIPTION_TIMEOUT"
    pid = int(pid_file.read_text(encoding="ascii"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_busy_request_is_rejected_before_upload_or_workspace_creation(
    fake_homr: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    started = tmp_path / "started"
    release = tmp_path / "release"
    monkeypatch.setenv("TMPDIR", str(workspace))
    monkeypatch.setenv("FAKE_HOMR_MODE", "blocking")
    monkeypatch.setenv("FAKE_HOMR_STARTED", str(started))
    monkeypatch.setenv("FAKE_HOMR_RELEASE", str(release))
    parsed_requests = 0
    original_one_upload = server._one_upload

    async def counted_one_upload(request):
        nonlocal parsed_requests
        parsed_requests += 1
        return await original_one_upload(request)

    monkeypatch.setattr(server, "_one_upload", counted_one_upload)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(post_png, client)
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists()
        active_workspaces = list(workspace.iterdir())
        assert len(active_workspaces) == 1

        busy_started = time.monotonic()
        second = post_png(client)
        busy_elapsed = time.monotonic() - busy_started
        assert second.status_code == 503
        assert second.json() == {
            "error": {"code": "SERVICE_BUSY", "message": "The OMR service is busy."}
        }
        assert busy_elapsed < 1
        assert list(workspace.iterdir()) == active_workspaces
        assert parsed_requests == 1
        assert len(fake_homr.read_text(encoding="utf-8").splitlines()) == 1

        release.touch()
        assert first.result(timeout=5).status_code == 200

    assert list(workspace.iterdir()) == []
