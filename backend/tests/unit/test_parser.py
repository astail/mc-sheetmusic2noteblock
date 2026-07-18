"""parser の完了条件: 6フィクスチャすべてがエラーなくパースでき、音数・音域が定義と一致。"""

from pathlib import Path

import pytest

from app.services.parser import parse_score

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_scale_c_major():
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml")
    assert parsed.summary.note_count == 8
    assert parsed.summary.midi_min == 60  # C4
    assert parsed.summary.midi_max == 72  # C5
    assert parsed.summary.original_bpm == 120
    # 4分音符が1拍ずつ並ぶ
    offsets = [e.offset_ql for e in parsed.events]
    assert offsets == [float(i) for i in range(8)]


def test_twinkle_both_hands_staves():
    parsed = parse_score(FIXTURES / "twinkle_both_hands.musicxml")
    # メロディ14音 + 和音4つ×3音(和音は個々のノートに展開)
    assert parsed.summary.note_count == 26
    assert parsed.summary.midi_min == 41  # F2
    assert parsed.summary.midi_max == 69  # A4
    assert parsed.summary.original_bpm == 100
    # 2譜表: staff 1 = 右手メロディ、staff 2 = 左手和音
    staves = {e.staff_number for e in parsed.events}
    assert staves == {1, 2}
    right = [e for e in parsed.events if e.staff_number == 1]
    left = [e for e in parsed.events if e.staff_number == 2]
    assert len(right) == 14
    assert len(left) == 12


def test_twinkle_midi():
    parsed = parse_score(FIXTURES / "twinkle.mid")
    assert parsed.summary.note_count == 26
    assert parsed.summary.midi_min == 41
    assert parsed.summary.midi_max == 69
    # MIDI は2トラック(右手/左手)
    melodic_tracks = [t for t in parsed.summary.tracks if t.note_count > 0]
    assert len(melodic_tracks) == 2
    track_indices = {e.track_index for e in parsed.events}
    assert len(track_indices) == 2


def test_tempo_change():
    parsed = parse_score(FIXTURES / "tempo_change.mid")
    assert parsed.summary.note_count == 8
    assert parsed.summary.original_bpm == 120  # 最初のテンポ


def test_extreme_range():
    parsed = parse_score(FIXTURES / "extreme_range.mid")
    assert parsed.summary.note_count == 4
    assert parsed.summary.midi_min == 21  # A0
    assert parsed.summary.midi_max == 108  # C8


def test_sixteenth_150bpm():
    parsed = parse_score(FIXTURES / "sixteenth_150bpm.mid")
    assert parsed.summary.note_count == 16
    assert parsed.summary.original_bpm == 150
    # 16分音符 = 0.25 ql 刻み
    offsets = [e.offset_ql for e in parsed.events]
    assert offsets == [i * 0.25 for i in range(16)]


def test_unsupported_extension_rejected():
    with pytest.raises(ValueError):
        parse_score(FIXTURES / "score.pdf")


def test_chord_notes_share_offset():
    parsed = parse_score(FIXTURES / "twinkle_both_hands.musicxml")
    left = [e for e in parsed.events if e.staff_number == 2]
    # 和音1つ = 同一 offset の3音
    first_chord = [e for e in left if e.offset_ql == 0.0]
    assert len(first_chord) == 3
    assert {e.midi_pitch for e in first_chord} == {48, 52, 55}  # C3 E3 G3
