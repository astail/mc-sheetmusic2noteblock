"""非同期 OMR ジョブ API から既存 score パイプラインまでを検証する。"""

from __future__ import annotations

import io
import json
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, storage
from app.api import omr
from app.main import app
from app.services.omr_client import OmrTranscriptionError, OmrUnavailableError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _mxl_fixture() -> bytes:
    output = io.BytesIO()
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles>
</container>"""
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr(
            "score.musicxml", (FIXTURES / "scale_c_major.musicxml").read_bytes()
        )
    return output.getvalue()


class SuccessfulOmr:
    async def ensure_available(self) -> None:
        return None

    async def transcribe(self, input_path: Path, source_filename: str) -> bytes:
        assert input_path.read_bytes() == b"%PDF-test"
        assert source_filename == "scan.pdf"
        return _mxl_fixture()


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _poll_done(client: TestClient, job_id: str) -> dict:
    for _ in range(200):
        response = client.get(f"/api/omr/jobs/{job_id}")
        assert response.status_code == 200
        if response.json()["status"] in {"done", "failed"}:
            return response.json()
        time.sleep(0.01)
    raise AssertionError("OMR job did not finish")


def test_job_transcribes_and_registers_normal_score():
    app.dependency_overrides[omr.get_omr_client] = SuccessfulOmr
    with TestClient(app) as client:
        response = client.post(
            "/api/omr/jobs",
            files={"file": ("scan.pdf", b"%PDF-test", "application/pdf")},
        )
        assert response.status_code == 202
        created = response.json()
        assert created["status"] == "queued"
        assert len(created["job_id"]) == 32

        result = _poll_done(client, created["job_id"])
        assert result["status"] == "done"
        assert result["error"] is None
        score_id = result["score_id"]
        assert len(score_id) == 32

        score = client.get(f"/api/scores/{score_id}")
        assert score.status_code == 200
        assert score.json()["summary"]["note_count"] == 8
        assert storage.original_path(score_id).suffix == ".mxl"
        assert storage.load_source_filename(score_id) == "scan.mxl"

        job_dir = storage.omr_job_dir(created["job_id"])
        assert {path.name for path in job_dir.iterdir()} == {"job.json"}


def test_profile_disabled_returns_clear_501_without_creating_job():
    class UnavailableOmr:
        async def ensure_available(self) -> None:
            raise OmrUnavailableError("internal host detail")

    app.dependency_overrides[omr.get_omr_client] = UnavailableOmr
    with TestClient(app) as client:
        response = client.post(
            "/api/omr/jobs",
            files={"file": ("scan.png", b"png", "image/png")},
        )

    assert response.status_code == 501
    assert "--profile omr" in response.json()["detail"]
    assert "internal host detail" not in response.text
    assert storage.iter_omr_jobs() == []


def test_jobs_are_queued_and_run_one_at_a_time():
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    class BlockingOmr:
        async def ensure_available(self) -> None:
            return None

        async def transcribe(self, _path: Path, _filename: str) -> bytes:
            nonlocal calls
            with calls_lock:
                calls += 1
                current = calls
            if current == 1:
                entered.set()
                while not release.is_set():
                    await __import__("asyncio").sleep(0.01)
            return _mxl_fixture()

    instance = BlockingOmr()
    app.dependency_overrides[omr.get_omr_client] = lambda: instance
    with TestClient(app) as client:
        first = client.post(
            "/api/omr/jobs", files={"file": ("one.pdf", b"1", "application/pdf")}
        ).json()
        assert entered.wait(timeout=2)
        second = client.post(
            "/api/omr/jobs", files={"file": ("two.pdf", b"2", "application/pdf")}
        ).json()

        second_state = client.get(f"/api/omr/jobs/{second['job_id']}").json()
        assert second_state["status"] == "queued"
        assert calls == 1

        release.set()
        assert _poll_done(client, first["job_id"])["status"] == "done"
        assert _poll_done(client, second["job_id"])["status"] == "done"
        assert calls == 2


def test_failed_transcription_has_fixed_public_error_and_cleans_input():
    class FailedOmr:
        async def ensure_available(self) -> None:
            return None

        async def transcribe(self, _path: Path, _filename: str) -> bytes:
            raise OmrTranscriptionError("private Audiveris stack trace")

    app.dependency_overrides[omr.get_omr_client] = FailedOmr
    with TestClient(app) as client:
        created = client.post(
            "/api/omr/jobs",
            files={"file": ("scan.jpeg", b"jpeg", "image/jpeg")},
        ).json()
        result = _poll_done(client, created["job_id"])

    assert result["status"] == "failed"
    assert result["score_id"] is None
    assert result["error"]["code"] == "OMR_FAILED"
    assert "private" not in json.dumps(result, ensure_ascii=False)
    assert {p.name for p in storage.omr_job_dir(created["job_id"]).iterdir()} == {
        "job.json"
    }
    scores_root = Path(config.DATA_DIR) / "scores"
    assert not scores_root.exists() or list(scores_root.iterdir()) == []


def test_interrupted_job_is_recovered_on_startup_and_input_is_cleaned():
    queued = storage.create_omr_job("scan.pdf", b"pending")
    storage.update_omr_job(queued.job_id, "running")

    with TestClient(app) as client:
        response = client.get(f"/api/omr/jobs/{queued.job_id}")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["error"]["code"] == "OMR_INTERRUPTED"
    assert {p.name for p in storage.omr_job_dir(queued.job_id).iterdir()} == {"job.json"}


def test_cancelled_registration_cleans_up_orphan_score(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original_register_score = omr._register_score

    def slow_register_score(source_filename: str, mxl_content: bytes) -> str:
        entered.set()
        release.wait(timeout=2)
        return original_register_score(source_filename, mxl_content)

    monkeypatch.setattr(omr, "_register_score", slow_register_score)
    app.dependency_overrides[omr.get_omr_client] = SuccessfulOmr
    with TestClient(app) as client:
        created = client.post(
            "/api/omr/jobs",
            files={"file": ("scan.pdf", b"%PDF-test", "application/pdf")},
        ).json()

        assert entered.wait(timeout=2)
        omr._tasks[created["job_id"]].cancel()
        release.set()

        result = _poll_done(client, created["job_id"])
        assert result["status"] == "failed"
        assert result["error"]["code"] == "OMR_INTERRUPTED"

        scores_root = Path(config.DATA_DIR) / "scores"
        assert not scores_root.exists() or list(scores_root.iterdir()) == []


def test_cancelled_finalize_does_not_discard_a_completed_job(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original_update_omr_job = storage.update_omr_job

    def slow_update_omr_job(job_id, status, **kwargs):
        if status == "done":
            entered.set()
            release.wait(timeout=2)
        return original_update_omr_job(job_id, status, **kwargs)

    monkeypatch.setattr(storage, "update_omr_job", slow_update_omr_job)
    app.dependency_overrides[omr.get_omr_client] = SuccessfulOmr
    with TestClient(app) as client:
        created = client.post(
            "/api/omr/jobs",
            files={"file": ("scan.pdf", b"%PDF-test", "application/pdf")},
        ).json()

        assert entered.wait(timeout=2)
        omr._tasks[created["job_id"]].cancel()
        release.set()

        result = _poll_done(client, created["job_id"])
        assert result["status"] == "done"
        assert result["error"] is None
        score_id = result["score_id"]

        score = client.get(f"/api/scores/{score_id}")
        assert score.status_code == 200


def test_invalid_upload_and_job_ids_are_rejected(monkeypatch):
    app.dependency_overrides[omr.get_omr_client] = SuccessfulOmr
    monkeypatch.setattr(omr, "MAX_UPLOAD_BYTES", 3)
    with TestClient(app) as client:
        unsupported = client.post(
            "/api/omr/jobs", files={"file": ("score.mid", b"midi")}
        )
        too_large = client.post(
            "/api/omr/jobs", files={"file": ("score.pdf", b"four")}
        )
        empty = client.post(
            "/api/omr/jobs", files={"file": ("score.pdf", b"")}
        )
        missing = client.get(f"/api/omr/jobs/{'0' * 32}")
        traversal = client.get("/api/omr/jobs/../../etc")

    assert unsupported.status_code == 415
    assert too_large.status_code == 413
    assert empty.status_code == 422
    assert missing.status_code == 404
    assert traversal.status_code in {404, 307}
    assert storage.iter_omr_jobs() == []


def test_corrupt_job_state_returns_generic_error():
    record = storage.create_omr_job("scan.png", b"png")
    (storage.omr_job_dir(record.job_id) / "job.json").write_text(
        "contains private filesystem details", encoding="utf-8"
    )

    with TestClient(app) as client:
        response = client.get(f"/api/omr/jobs/{record.job_id}")

    assert response.status_code == 500
    assert response.json()["detail"] == "OMRジョブの状態を読み取れません"
    assert "private" not in response.text
