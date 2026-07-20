"""storage の完了条件: 保存した score をプロセスをまたいでも(=ディスクから)読み戻せる。"""

import json
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
    assert files == {"original.mid", "parsed.json", "blueprint.json", "source_filename.txt"}


def test_source_filename_preserved():
    # アップロード時の表示名が永続化され、後段の Blueprint.meta.source_file に使える
    score_id = storage.create_score("きらきら星.mid", b"midi")
    assert storage.load_source_filename(score_id) == "きらきら星.mid"
    # パス付きで来ても名前部分のみ保存する
    score_id2 = storage.create_score("dir/sub/twinkle.mid", b"midi")
    assert storage.load_source_filename(score_id2) == "twinkle.mid"


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


def test_legacy_parsed_summary_is_reparsed_and_migrated():
    score_id = storage.create_score(
        "twinkle.mid", (FIXTURES / "twinkle.mid").read_bytes()
    )
    parsed_path = storage.score_dir(score_id) / "parsed.json"
    parsed_path.write_bytes(
        (FIXTURES / "legacy_parsed_without_measure_count.json").read_bytes()
    )

    summary = storage.load_parsed(score_id)

    assert summary is not None
    assert summary.measure_count == 4
    migrated = json.loads(parsed_path.read_text(encoding="utf-8"))
    assert migrated["measure_count"] == 4
    assert migrated["tracks"][0]["part_id"] != "legacy-track-0"


def test_legacy_parsed_summary_with_unparseable_original_returns_none():
    score_id = storage.create_score("broken.mid", b"not a midi file")
    parsed_path = storage.score_dir(score_id) / "parsed.json"
    legacy = (FIXTURES / "legacy_parsed_without_measure_count.json").read_bytes()
    parsed_path.write_bytes(legacy)

    assert storage.load_parsed(score_id) is None
    assert parsed_path.read_bytes() == legacy


def test_legacy_parsed_summary_is_returned_when_migration_write_fails(monkeypatch):
    score_id = storage.create_score(
        "twinkle.mid", (FIXTURES / "twinkle.mid").read_bytes()
    )
    parsed_path = storage.score_dir(score_id) / "parsed.json"
    legacy = (FIXTURES / "legacy_parsed_without_measure_count.json").read_bytes()
    parsed_path.write_bytes(legacy)

    def _raise_write_error(_score_id, _summary):
        raise OSError("read-only")

    monkeypatch.setattr(storage, "save_parsed", _raise_write_error)

    summary = storage.load_parsed(score_id)

    assert summary is not None
    assert summary.measure_count == 4
    assert parsed_path.read_bytes() == legacy
