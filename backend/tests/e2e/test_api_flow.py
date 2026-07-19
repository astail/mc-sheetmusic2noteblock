"""E2E: アップロード → 設計書生成 → 再取得 の一気通貫を1つのフローとして数値検証する。

(docs/IMPLEMENTATION_PLAN.md「E2E」。個別 API の異常系は test_api_scores / test_api_blueprint も参照)
"""

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


def test_upload_to_blueprint_flow():
    # 1. アップロード → score_id とサマリ
    res = client.post(
        "/api/scores",
        files={
            "file": (
                "scale_c_major.musicxml",
                (FIXTURES / "scale_c_major.musicxml").read_bytes(),
            )
        },
    )
    assert res.status_code == 200
    uploaded = res.json()
    score_id = uploaded["score_id"]
    assert uploaded["summary"]["note_count"] == 8
    assert uploaded["recommended_tpq"] == 5  # 120BPM → 実効120BPM の tpq5

    # 2. 変換実行(tpq=4) → 完了条件の数値
    res = client.post(f"/api/scores/{score_id}/blueprint", json={"ticks_per_quarter": 4})
    assert res.status_code == 200
    blueprint = res.json()
    assert blueprint["meta"]["step_count"] == 8
    assert [s["delay_from_prev_rticks"] for s in blueprint["steps"]] == [0] + [4] * 7
    # 全 delay=4 はリピーター1個(4目盛)
    for step in blueprint["steps"][1:]:
        assert step["repeaters"] == {"chain": [4], "count": 1}
    notes = [n for s in blueprint["steps"] for n in s["notes"]]
    assert all(n["instrument"] == "harp" for n in notes)
    assert notes[0]["note_name"] == "C4"
    assert notes[0]["clicks"] == 6

    # 3. 再取得(サマリ・設計書とも保存済みのものが返る)
    res = client.get(f"/api/scores/{score_id}")
    assert res.status_code == 200
    assert res.json() == uploaded
    res = client.get(f"/api/scores/{score_id}/blueprint")
    assert res.status_code == 200
    assert res.json() == blueprint


def test_flow_error_cases():
    # 不正ファイルは 422
    res = client.post(
        "/api/scores", files={"file": ("broken.mid", b"not a midi file")}
    )
    assert res.status_code == 422
    # 未知 id は 404(サマリ・設計書とも)
    unknown = "f" * 32
    assert client.get(f"/api/scores/{unknown}").status_code == 404
    assert client.get(f"/api/scores/{unknown}/blueprint").status_code == 404
    assert (
        client.post(f"/api/scores/{unknown}/blueprint", json={}).status_code == 404
    )
