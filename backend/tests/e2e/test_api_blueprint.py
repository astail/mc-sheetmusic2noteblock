"""blueprint API の完了条件: scale + tpq=4 で steps=8、全 delay=4、全音 harp、C4=6クリック。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, storage
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


def test_custom_preset_without_ranges_returns_422():
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"instrument_preset": "custom"}
    )
    assert res.status_code == 422


def test_custom_preset_with_ranges_maps_notes_to_chosen_instrument():
    score_id = _upload("scale_c_major.musicxml")  # C4(60)〜C5(72) の8音
    res = client.post(
        f"/api/scores/{score_id}/blueprint",
        json={
            "instrument_preset": "custom",
            "custom_ranges": [{"instrument": "harp", "range_start_midi": 54}],
        },
    )
    assert res.status_code == 200
    bp = res.json()
    notes = [n for s in bp["steps"] for n in s["notes"]]
    assert all(n["instrument"] == "harp" for n in notes)
    assert notes[0]["clicks"] == 6  # C4(60) - harp の基準音(54)
    assert notes[-1]["clicks"] == 18  # C5(72) - harp の基準音(54)


def test_measure_range_converts_only_selected_musicxml_measure():
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint",
        json={"ticks_per_quarter": 4, "measure_range": [2, 2]},
    )
    assert res.status_code == 200
    bp = res.json()
    assert [step["tick"] for step in bp["steps"]] == [0, 4, 8, 12]
    assert bp["meta"]["step_count"] == 4
    notes = [note for step in bp["steps"] for note in step["notes"]]
    assert {note["source"]["measure"] for note in notes} == {2}


def test_measure_range_outside_score_returns_422():
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint",
        json={"ticks_per_quarter": 4, "measure_range": [2, 3]},
    )
    assert res.status_code == 422
    assert "1〜2" in res.json()["detail"]


def test_measure_range_rebases_midi_seconds_mode():
    score_id = _upload("tempo_change.mid")
    res = client.post(
        f"/api/scores/{score_id}/blueprint",
        json={"mode": "seconds", "measure_range": [2, 2]},
    )
    assert res.status_code == 200
    assert [step["tick"] for step in res.json()["steps"]] == [0, 7, 13, 20]


def test_measure_range_migrates_legacy_summary_before_blueprint():
    score_id = _upload("twinkle.mid")
    parsed_path = storage.score_dir(score_id) / "parsed.json"
    parsed_path.write_bytes(
        (FIXTURES / "legacy_parsed_without_measure_count.json").read_bytes()
    )

    res = client.post(
        f"/api/scores/{score_id}/blueprint",
        json={"ticks_per_quarter": 4, "measure_range": [4, 4]},
    )

    assert res.status_code == 200
    notes = [note for step in res.json()["steps"] for note in step["notes"]]
    assert {note["source"]["measure"] for note in notes} == {4}
    migrated = storage.load_parsed(score_id)
    assert migrated is not None
    assert migrated.measure_count == 4


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


def test_repeater_limit_warning_uses_config_threshold(monkeypatch):
    monkeypatch.setattr(config, "REPEATER_WARNING_THRESHOLD", 6)
    score_id = _upload("scale_c_major.musicxml")
    res = client.post(
        f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 4}
    )
    assert res.status_code == 200
    warning = next(w for w in res.json()["warnings"] if w["type"] == "repeater_limit")
    assert "リピーター総数は7個" in warning["message"]
    assert "曲を分割して複数の演奏装置に" in warning["message"]
    assert warning["steps"] is None


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


def test_repeated_notes_reuse_the_same_block():
    # twinkle.mid の冒頭「ドド」(同音連打)は近接する2ステップで同じ(harp,6クリック)
    # になるため、配線距離内でブロックが再利用される
    score_id = _upload("twinkle.mid")
    res = client.post(f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 4})
    assert res.status_code == 200
    bp = res.json()
    notes = [n for s in bp["steps"] for n in s["notes"]]
    assert len(notes) == 26
    assert bp["materials"]["note_block"] < 26
    reused = [n for n in notes if n["reused_from_step"] is not None]
    assert len(reused) > 0
    for n in reused:
        assert n["block_id"] is not None
    assert any("再利用" in note for note in bp["materials"]["notes"])
    reuse_warning = next(w for w in bp["warnings"] if w["type"] == "block_reuse")
    assert "本線バス" in reuse_warning["message"]
    assert len(reuse_warning["steps"]) > 0
    # 再利用のたびに迂回配線ぶんのダストが通常のステップ数×2の見積りに上乗せされる
    assert bp["materials"]["redstone_dust_estimate"] > len(bp["steps"]) * 2
