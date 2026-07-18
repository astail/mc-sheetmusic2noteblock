"""docs/DESIGN.md §7 の JSON 例がそのままバリデーションを通ることの確認。"""

import pytest
from pydantic import ValidationError

from app.models.blueprint import Blueprint, NotePlacement
from app.models.events import NoteEvent
from app.models.settings import ConversionSettings

# DESIGN.md §7 ConversionSettings の例(コメント除去)
CONVERSION_SETTINGS_EXAMPLE = {
    "mode": "beat",
    "ticks_per_quarter": 4,
    "tempo_scale": 1.0,
    "instrument_preset": "bass_harp_bell",
    "custom_ranges": None,
    "transpose_semitones": 0,
    "hand_assignment": {"track_0": "right", "track_1": "left"},
    "measure_range": None,
}

# DESIGN.md §7 Blueprint の例
BLUEPRINT_EXAMPLE = {
    "meta": {
        "title": "きらきら星",
        "source_file": "twinkle.mid",
        "original_bpm": 100,
        "effective_bpm": 100,
        "ticks_per_quarter": 6,
        "total_rticks": 384,
        "duration_seconds": 38.4,
        "step_count": 96,
        "quantization": {
            "max_error_ms": 33,
            "mean_error_ms": 8,
            "moved_notes": 12,
            "merged_notes": 2,
        },
    },
    "steps": [
        {
            "index": 12,
            "tick": 48,
            "time_seconds": 4.8,
            "delay_from_prev_rticks": 7,
            "repeaters": {"chain": [4, 3], "count": 2},
            "notes": [
                {
                    "instrument": "harp",
                    "instrument_ja": "ハープ",
                    "base_block": "dirt",
                    "base_block_ja": "土(デフォルト系)",
                    "clicks": 6,
                    "note_name": "C4",
                    "midi": 60,
                    "hand": "right",
                    "octave_shift": 0,
                    "source": {"measure": 5, "beat": 2.5, "part": "P1"},
                },
                {
                    "instrument": "bass",
                    "instrument_ja": "ベース",
                    "base_block": "oak_planks",
                    "base_block_ja": "オークの板材",
                    "clicks": 6,
                    "note_name": "C3",
                    "midi": 48,
                    "hand": "left",
                    "octave_shift": 0,
                },
            ],
        }
    ],
    "materials": {
        "note_block": 214,
        "repeater": 350,
        "redstone_dust_estimate": 180,
        "base_blocks": {"dirt": 120, "oak_planks": 74, "gold_block": 20},
        "notes": ["音符ブロックの真上は空気にすること", "起動用ボタン/レバー 1個"],
    },
    "warnings": [
        {
            "type": "octave_shift",
            "message": "A0〜B1 の 4音は bass 音域に収めるため +1〜+2 オクターブしました",
            "steps": [3, 17],
        },
        {
            "type": "big_chord",
            "message": "ステップ42は同時7音です。分岐ダストを両側に伸ばす配線を推奨",
            "steps": [42],
        },
        {
            "type": "tempo_change",
            "message": "原曲にテンポ変化があります。beat モードでは一定テンポ(100BPM)に平坦化されます",
        },
    ],
    "layout": {
        "type": "comb_bus",
        "description": "リピーターを +X 方向に直列。各ステップ位置から ±Z 方向へダスト分岐し音符ブロックを設置",
        "segments": [
            {"step_index": 12, "bus_offset_blocks": 25, "branch_sides": ["north", "south"]}
        ],
    },
}


def test_conversion_settings_example_validates():
    settings = ConversionSettings.model_validate(CONVERSION_SETTINGS_EXAMPLE)
    assert settings.mode == "beat"
    assert settings.hand_assignment == {"track_0": "right", "track_1": "left"}


def test_conversion_settings_defaults():
    settings = ConversionSettings()
    assert settings.mode == "beat"
    assert settings.ticks_per_quarter == 4
    assert settings.instrument_preset == "bass_harp_bell"


def test_blueprint_example_validates():
    bp = Blueprint.model_validate(BLUEPRINT_EXAMPLE)
    assert bp.meta.step_count == 96
    assert bp.steps[0].repeaters.chain == [4, 3]
    assert bp.steps[0].notes[0].source.measure == 5
    assert bp.steps[0].notes[1].source is None
    assert bp.warnings[2].steps is None
    assert bp.layout.segments[0].branch_sides == ["north", "south"]


def test_blueprint_without_layout():
    # MVP(blueprint_builder)は layout を生成しない
    payload = {k: v for k, v in BLUEPRINT_EXAMPLE.items() if k != "layout"}
    bp = Blueprint.model_validate(payload)
    assert bp.layout is None


def test_tempo_scale_must_be_positive():
    with pytest.raises(ValidationError):
        ConversionSettings(tempo_scale=0)
    with pytest.raises(ValidationError):
        ConversionSettings(tempo_scale=-1.5)


def test_clicks_must_be_in_noteblock_range():
    note = BLUEPRINT_EXAMPLE["steps"][0]["notes"][0]
    for bad_clicks in (-1, 25):
        with pytest.raises(ValidationError):
            NotePlacement.model_validate({**note, "clicks": bad_clicks})


def test_note_event_minimal():
    ev = NoteEvent(
        offset_ql=0.0,
        duration_ql=1.0,
        midi_pitch=60,
        part_id="P1",
        track_index=0,
    )
    assert ev.tie is None
    assert ev.staff_number is None
