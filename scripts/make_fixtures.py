"""music21 でテスト用フィクスチャ6種を backend/tests/fixtures/ に生成する。

実行: python scripts/make_fixtures.py
(docs/IMPLEMENTATION_PLAN.md「テスト戦略」参照)
"""

from pathlib import Path

from music21 import chord, clef, layout, meter, note, stream, tempo

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"

# きらきら星の前半(4/4 × 4小節)。(音名, quarterLength)
TWINKLE_MELODY = [
    ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1),
    ("A4", 1), ("A4", 1), ("G4", 2),
    ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1),
    ("D4", 1), ("D4", 1), ("C4", 2),
]
# 左手和音(1小節 = 全音符1つ)
TWINKLE_CHORDS = [
    (["C3", "E3", "G3"], 4),
    (["C3", "E3", "G3"], 4),
    (["F2", "A2", "C3"], 4),
    (["C3", "E3", "G3"], 4),
]


def scale_c_major() -> stream.Score:
    """4分音符のドレミ8音(最小ケース)。"""
    part = stream.Part(id="P1")
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(number=120))
    for pitch in ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]:
        part.append(note.Note(pitch, quarterLength=1))
    score = stream.Score()
    score.append(part)
    return score


def twinkle_both_hands() -> stream.Score:
    """右手メロディ+左手和音の2譜表(きらきら星の前半)。

    PartStaff + StaffGroup でピアノ譜(1パート2譜表)として出力し、
    MusicXML に <staff> 要素が入るようにする(手判別 #10 の検証対象)。
    """
    right = stream.PartStaff(id="RH")
    right.append(clef.TrebleClef())
    right.append(meter.TimeSignature("4/4"))
    right.append(tempo.MetronomeMark(number=100))
    for pitch, ql in TWINKLE_MELODY:
        right.append(note.Note(pitch, quarterLength=ql))

    left = stream.PartStaff(id="LH")
    left.append(clef.BassClef())
    left.append(meter.TimeSignature("4/4"))
    for pitches, ql in TWINKLE_CHORDS:
        left.append(chord.Chord(pitches, quarterLength=ql))

    score = stream.Score()
    score.insert(0, right)
    score.insert(0, left)
    score.insert(0, layout.StaffGroup([right, left], symbol="brace"))
    return score


def tempo_change() -> stream.Score:
    """途中で BPM が 120 → 90 に変化する。"""
    part = stream.Part(id="P1")
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(number=120))
    for pitch in ["C4", "E4", "G4", "C5"]:
        part.append(note.Note(pitch, quarterLength=1))
    part.append(tempo.MetronomeMark(number=90))
    for pitch in ["C5", "G4", "E4", "C4"]:
        part.append(note.Note(pitch, quarterLength=1))
    score = stream.Score()
    score.append(part)
    return score


def extreme_range() -> stream.Score:
    """A0(MIDI 21)と C8(MIDI 108)を含む(オクターブシフト警告用)。"""
    part = stream.Part(id="P1")
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(number=120))
    for pitch in ["A0", "C4", "C8", "A0"]:
        part.append(note.Note(pitch, quarterLength=1))
    score = stream.Score()
    score.append(part)
    return score


def sixteenth_150bpm() -> stream.Score:
    """150BPM の16分音符×16(誤差ゼロ量子化用)。"""
    part = stream.Part(id="P1")
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(number=150))
    for i in range(16):
        pitch = ["C4", "D4", "E4", "F4"][i % 4]
        part.append(note.Note(pitch, quarterLength=0.25))
    score = stream.Score()
    score.append(part)
    return score


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        (scale_c_major(), "musicxml", "scale_c_major.musicxml"),
        (twinkle_both_hands(), "musicxml", "twinkle_both_hands.musicxml"),
        (twinkle_both_hands(), "midi", "twinkle.mid"),
        (tempo_change(), "midi", "tempo_change.mid"),
        (extreme_range(), "midi", "extreme_range.mid"),
        (sixteenth_150bpm(), "midi", "sixteenth_150bpm.mid"),
    ]
    for score, fmt, filename in outputs:
        path = FIXTURES_DIR / filename
        score.write(fmt, fp=path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
