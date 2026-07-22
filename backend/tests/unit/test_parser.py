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
    assert parsed.summary.measure_count == 2


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
    assert parsed.summary.measure_count == 4


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


def test_drum_beat_percussion_track():
    # channel 10 は GM percussion map の実キー番号を midi_pitch として展開する
    parsed = parse_score(FIXTURES / "drum_beat.mid")
    assert parsed.summary.note_count == 5
    percussion_tracks = [t for t in parsed.summary.tracks if t.is_percussion]
    assert len(percussion_tracks) == 1
    assert percussion_tracks[0].note_count == 5
    assert [e.channel for e in parsed.events] == [10] * 5
    # bass drum(36), snare(38), closed hihat(42), open hihat(46), crash(49)
    assert [e.midi_pitch for e in parsed.events] == [36, 38, 42, 46, 49]


def test_original_bpm_normalized_to_quarter_bpm(tmp_path):
    from music21 import meter, note, stream, tempo

    part = stream.Part(id="P1")
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(referent="half", number=60))  # 2分音符=60 → 実質120BPM
    part.append(note.Note("C4", quarterLength=1))
    score = stream.Score()
    score.append(part)
    path = tmp_path / "half_note_tempo.musicxml"
    score.write("musicxml", fp=path)

    parsed = parse_score(path)
    assert parsed.summary.original_bpm == 120


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


def test_musicxml_measure_range_is_inclusive_and_rebased():
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml", measure_range=(2, 2))

    assert parsed.summary.note_count == 4
    assert parsed.summary.duration_ql == 4
    assert [e.offset_ql for e in parsed.events] == [0.0, 1.0, 2.0, 3.0]
    assert {e.measure for e in parsed.events} == {2}


def test_midi_measure_range_uses_generated_measures():
    parsed = parse_score(FIXTURES / "twinkle.mid", measure_range=(3, 4))

    assert parsed.summary.measure_count == 4
    assert parsed.summary.note_count == 13
    assert min(e.offset_ql for e in parsed.events) == 0
    assert max(e.offset_ql for e in parsed.events) == 6
    assert {e.measure for e in parsed.events} == {3, 4}


def test_measure_range_rebases_seconds_with_tempo_change():
    parsed = parse_score(FIXTURES / "tempo_change.mid", measure_range=(2, 2))

    assert [e.offset_seconds for e in parsed.events] == pytest.approx(
        [0.0, 2 / 3, 4 / 3, 2.0]
    )


def test_measure_range_preserves_rest_before_first_note(tmp_path):
    from music21 import meter, note, stream

    part = stream.Part(id="P1")
    first = stream.Measure(number=1)
    first.append(meter.TimeSignature("4/4"))
    first.append(note.Rest(quarterLength=4))
    second = stream.Measure(number=2)
    second.append(note.Rest(quarterLength=1))
    second.append(note.Note("C4", quarterLength=1))
    second.append(note.Rest(quarterLength=2))
    part.append([first, second])
    score = stream.Score([part])
    path = tmp_path / "leading-rest.musicxml"
    score.write("musicxml", fp=path)

    parsed = parse_score(path, measure_range=(2, 2))

    assert [e.offset_ql for e in parsed.events] == [1.0]


def test_measure_range_outside_score_is_rejected():
    with pytest.raises(ValueError, match="1〜2"):
        parse_score(FIXTURES / "scale_c_major.musicxml", measure_range=(2, 3))
