"""POST /api/scores の完了条件: フィクスチャを multipart で投げてサマリ JSON が返る。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)


def _upload(filename: str, content: bytes, mime: str = "application/octet-stream"):
    return client.post("/api/scores", files={"file": (filename, content, mime)})


def test_upload_twinkle_mid_returns_summary():
    res = _upload("twinkle.mid", (FIXTURES / "twinkle.mid").read_bytes())
    assert res.status_code == 200
    body = res.json()
    assert len(body["score_id"]) == 32
    assert body["summary"]["note_count"] == 26
    assert body["summary"]["original_bpm"] == 100
    assert body["summary"]["midi_min"] == 41
    assert body["summary"]["midi_max"] == 69
    assert len(body["summary"]["tracks"]) == 2
    assert body["recommended_tpq"] == 6  # 100BPM → tpq6(実効100BPM)


def test_upload_musicxml_returns_summary():
    res = _upload(
        "scale_c_major.musicxml", (FIXTURES / "scale_c_major.musicxml").read_bytes()
    )
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["note_count"] == 8
    assert body["recommended_tpq"] == 5  # 120BPM → tpq5(実効120BPM)


def test_upload_pdf_returns_501():
    res = _upload("score.pdf", b"%PDF-1.4")
    assert res.status_code == 501


def test_upload_unknown_extension_returns_415():
    res = _upload("song.txt", b"not a score")
    assert res.status_code == 415


def test_get_score_returns_same_summary_as_post():
    posted = _upload("twinkle.mid", (FIXTURES / "twinkle.mid").read_bytes()).json()
    res = client.get(f"/api/scores/{posted['score_id']}")
    assert res.status_code == 200
    # 完了条件: POST 直後と(ディスクからの読み戻し=再起動相当で)同じサマリが返る
    assert res.json() == posted


def test_get_unknown_score_returns_404():
    assert client.get(f"/api/scores/{'0' * 32}").status_code == 404


def test_get_invalid_score_id_returns_404():
    assert client.get("/api/scores/not-a-valid-id").status_code == 404


def test_upload_broken_midi_returns_422_and_cleans_up():
    res = _upload("broken.mid", b"this is not midi data")
    assert res.status_code == 422
    # 保存物が残らない
    scores_root = Path(config.DATA_DIR) / "scores"
    assert not scores_root.exists() or list(scores_root.iterdir()) == []
