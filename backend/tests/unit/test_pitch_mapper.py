"""pitch_mapper の完了条件: C4→harp 6クリック、extreme_range の A0/C8 がシフト+警告付き。"""

from pathlib import Path

import pytest

from app.services.parser import parse_score
from app.services.pitch_mapper import build_octave_shift_warning, map_percussion, map_pitch

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


def test_harp_only_everything_maps_to_harp():
    # 完了条件: どんな入力でも出力が全て harp になる
    for midi in (21, 30, 53, 54, 60, 78, 79, 102, 108):
        mapped = map_pitch(midi, preset="harp_only")
        assert mapped.instrument == "harp"
        assert 0 <= mapped.clicks <= 24


def test_harp_only_octave_folding():
    # 域内はそのまま
    assert map_pitch(60, preset="harp_only").octave_shift == 0
    assert map_pitch(60, preset="harp_only").clicks == 6
    # 低音は上に折込: A0(21) → +3 オクターブ = 57
    low = map_pitch(21, preset="harp_only")
    assert (low.octave_shift, low.clicks) == (3, 3)
    # 高音は下に折込: C8(108) → -3 オクターブ = 72
    high = map_pitch(108, preset="harp_only")
    assert (high.octave_shift, high.clicks) == (-3, 18)


def test_harp_only_fixture_warning_counts_folded_notes():
    # 完了条件: シフト数が警告に出る
    parsed = parse_score(FIXTURES / "extreme_range.mid")
    mapped = [map_pitch(e.midi_pitch, preset="harp_only") for e in parsed.events]
    warning = build_octave_shift_warning(mapped)
    assert warning is not None
    assert warning.type == "octave_shift"
    assert "3音" in warning.message  # A0×2 + C8(C4 は域内)


def test_harp_only_with_transpose():
    mapped = map_pitch(53, preset="harp_only", transpose_semitones=1)  # 54 ちょうど
    assert (mapped.instrument, mapped.clicks, mapped.octave_shift) == ("harp", 0, 0)


def test_percussion_maps_gm_keys_to_three_timbres():
    # bass drum / snare / closed+open hi-hat / crash(RESEARCH.md §1 の打楽器3音色)
    assert map_percussion(36).instrument == "basedrum"
    assert map_percussion(38).instrument == "snare"
    assert map_percussion(42).instrument == "hat"
    assert map_percussion(46).instrument == "hat"
    assert map_percussion(49).instrument == "hat"


def test_percussion_always_uses_base_click_with_no_shift():
    for key in (36, 38, 42):
        mapped = map_percussion(key)
        assert mapped.clicks == 0
        assert mapped.octave_shift == 0


def test_percussion_unknown_key_falls_back_to_snare():
    assert map_percussion(1).instrument == "snare"
