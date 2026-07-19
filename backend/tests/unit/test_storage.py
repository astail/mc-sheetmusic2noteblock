"""storage の完了条件: 保存した score をプロセスをまたいでも(=ディスクから)読み戻せる。"""

from pathlib import Path

import pytest

from app import config, storage
from app.models.blueprint import (
    Blueprint,
    Materials,
    Meta,
    QuantizationStats,
)
from app.services.parser import ScoreSummary

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)


def _summary() -> ScoreSummary:
    return ScoreSummary(
        title="きらきら星",
        original_bpm=100.0,
        note_count=26,
        duration_ql=16.0,
        tracks=[],
    )


def _blueprint() -> Blueprint:
    return Blueprint(
        meta=Meta(
            title="きらきら星",
            source_file="twinkle.mid",
            original_bpm=100.0,
            effective_bpm=150.0,
            ticks_per_quarter=4,
            total_rticks=60,
            duration_seconds=6.0,
            step_count=1,
            quantization=QuantizationStats(
                max_error_ms=0, mean_error_ms=0, moved_notes=0, merged_notes=0
            ),
        ),
        steps=[],
        materials=Materials(
            note_block=0, repeater=0, redstone_dust_estimate=0, base_blocks={}, notes=[]
        ),
        warnings=[],
    )


def test_create_score_saves_original_with_extension():
    content = (FIXTURES / "twinkle.mid").read_bytes()
    score_id = storage.create_score("twinkle.mid", content)
    assert storage.score_exists(score_id)
    original = storage.original_path(score_id)
    assert original is not None
    assert original.name == "original.mid"
    assert original.read_bytes() == content


def test_parsed_and_blueprint_roundtrip():
    score_id = storage.create_score("twinkle.mid", b"midi")
    storage.save_parsed(score_id, _summary())
    storage.save_blueprint(score_id, _blueprint())

    # ディスクに永続化されているので、読み戻しはファイルのみに依存する
    loaded_summary = storage.load_parsed(score_id)
    assert loaded_summary == _summary()
    loaded_blueprint = storage.load_blueprint(score_id)
    assert loaded_blueprint == _blueprint()

    files = {p.name for p in storage.score_dir(score_id).iterdir()}
    assert files == {"original.mid", "parsed.json", "blueprint.json"}


def test_missing_returns_none():
    score_id = storage.create_score("a.mid", b"x")
    assert storage.load_parsed(score_id) is None
    assert storage.load_blueprint(score_id) is None
    unknown = "0" * 32
    assert not storage.score_exists(unknown)
    assert storage.original_path(unknown) is None


def test_invalid_score_id_rejected():
    for bad in ("../../etc", "abc", "ABCDEF0123456789ABCDEF0123456789", "0" * 31):
        with pytest.raises(ValueError):
            storage.score_dir(bad)
