"""blueprint API の完了条件: scale + tpq=4 で steps=8、全 delay=4、全音 harp、C4=6クリック。"""

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


def _upload(fixture: str) -> str:
    res = client.post(
        "/api/scores",
        files={"file": (fixture, (FIXTURES / fixture).read_bytes())},
    )
    assert res.status_code == 200
    return res.json()["score_id"]


def test_scale_blueprint_matches_expected_numbers():
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 4}
    )
    assert res.status_code == 200
    bp = res.json()
    # 完了条件の数値
    assert bp["meta"]["step_count"] == 8
    delays = [s["delay_from_prev_rticks"] for s in bp["steps"]]
    assert delays == [0] + [4] * 7
    notes = [n for s in bp["steps"] for n in s["notes"]]
    assert all(n["instrument"] == "harp" for n in notes)
    assert notes[0]["note_name"] == "C4"
    assert notes[0]["clicks"] == 6
    assert bp["meta"]["effective_bpm"] == 150
    assert bp["materials"]["note_block"] == 8
    assert bp["meta"]["source_file"] == "scale_c_major.musicxml"


def test_blueprint_persisted_and_returned_by_get():
    score_id = _upload("scale_c_major.musicxml")
    posted = client.post(
        f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 4}
    ).json()
    res = client.get(f"/api/scores/{score_id}/blueprint")
    assert res.status_code == 200
    assert res.json() == posted


def test_get_before_post_returns_404():
    score_id = _upload("scale_c_major.musicxml")
    assert client.get(f"/api/scores/{score_id}/blueprint").status_code == 404


def test_post_unknown_score_returns_404():
    res = client.post(f"/api/scores/{'0' * 32}/blueprint", json={})
    assert res.status_code == 404


def test_invalid_settings_returns_422():
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 7}
    )
    assert res.status_code == 422


def test_custom_preset_returns_422_until_implemented():
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"instrument_preset": "custom"}
    )
    assert res.status_code == 422


def test_seconds_mode_on_tempo_change():
    score_id = _upload("tempo_change.mid")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"mode": "seconds"}
    )
    assert res.status_code == 200
    bp = res.json()
    assert bp["meta"]["effective_bpm"] is None
    assert bp["meta"]["ticks_per_quarter"] is None
    ticks = [s["tick"] for s in bp["steps"]]
    assert ticks == [0, 5, 10, 15, 20, 27, 33, 40]


def test_beat_mode_on_tempo_change_warns():
    score_id = _upload("tempo_change.mid")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 4}
    )
    assert res.status_code == 200
    warning_types = {w["type"] for w in res.json()["warnings"]}
    assert "tempo_change" in warning_types


def test_hand_assignment_override_applies():
    score_id = _upload("twinkle.mid")
    res = client.post(
        f"/api/scores/{score_id}/blueprint",
        json={"ticks_per_quarter": 4, "hand_assignment": {"track_0": "ignore", "track_1": "left"}},
    )
    assert res.status_code == 200
    notes = [n for s in res.json()["steps"] for n in s["notes"]]
    assert all(n["hand"] == "left" for n in notes)
    assert len(notes) == 12  # track_0(メロディ14音)は ignore で除外
