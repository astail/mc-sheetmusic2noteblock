"""pitch_mapper の完了条件: C4→harp 6クリック、extreme_range の A0/C8 がシフト+警告付き。"""

from pathlib import Path

import pytest

from app.services.parser import parse_score
from app.services.pitch_mapper import build_octave_shift_warning, map_pitch

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_c4_maps_to_harp_6_clicks():
    mapped = map_pitch(60)
    assert mapped.instrument == "harp"
    assert mapped.clicks == 6
    assert mapped.octave_shift == 0


def test_boundary_values():
    # IMPLEMENTATION_PLAN.md: 境界値 MIDI 30・54・78・102
    assert map_pitch(30).instrument == "bass"
    assert map_pitch(30).clicks == 0
    assert map_pitch(53).instrument == "bass"
    assert map_pitch(53).clicks == 23
    # 境界 54・78 は harp 優先
    assert map_pitch(54).instrument == "harp"
    assert map_pitch(54).clicks == 0
    assert map_pitch(78).instrument == "harp"
    assert map_pitch(78).clicks == 24
    assert map_pitch(79).instrument == "bell"
    assert map_pitch(79).clicks == 1
    assert map_pitch(102).instrument == "bell"
    assert map_pitch(102).clicks == 24


def test_low_pitch_shifts_up():
    mapped = map_pitch(21)  # A0
    assert mapped.instrument == "bass"
    assert mapped.octave_shift == 1  # 21 + 12 = 33
    assert mapped.clicks == 3


def test_high_pitch_shifts_down():
    mapped = map_pitch(108)  # C8
    assert mapped.instrument == "bell"
    assert mapped.octave_shift == -1  # 108 - 12 = 96
    assert mapped.clicks == 18


def test_transpose_applied_before_mapping():
    mapped = map_pitch(60, transpose_semitones=12)  # C5 相当
    assert mapped.instrument == "harp"
    assert mapped.clicks == 18
    # transpose で音域外に出た場合もシフトされる
    mapped2 = map_pitch(102, transpose_semitones=12)
    assert mapped2.octave_shift == -1
    assert mapped2.instrument == "bell"
    assert mapped2.clicks == 24


def test_extreme_range_fixture_shifts_with_warning():
    parsed = parse_score(FIXTURES / "extreme_range.mid")
    mapped = [map_pitch(e.midi_pitch) for e in parsed.events]
    # A0×2 と C8 の3音がシフト対象
    shifted = [m for m in mapped if m.octave_shift != 0]
    assert len(shifted) == 3
    warning = build_octave_shift_warning(mapped)
    assert warning is not None
    assert warning.type == "octave_shift"
    assert "3音" in warning.message


def test_no_warning_when_all_in_range():
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml")
    mapped = [map_pitch(e.midi_pitch) for e in parsed.events]
    assert build_octave_shift_warning(mapped) is None


def test_unknown_preset_rejected():
    with pytest.raises(ValueError):
        map_pitch(60, preset="unknown")
