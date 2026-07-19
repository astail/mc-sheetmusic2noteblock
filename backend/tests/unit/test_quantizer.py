"""quantizer(拍グリッド)の完了条件: sixteenth_150bpm.mid + tpq=4 で全ノート誤差 0。"""

from pathlib import Path

from app.models.events import NoteEvent
from app.services.parser import parse_score
from app.services.quantizer import quantize_beats, recommend_tpq

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _event(offset_ql: float, midi: int = 60) -> NoteEvent:
    return NoteEvent(
        offset_ql=offset_ql,
        duration_ql=0.25,
        midi_pitch=midi,
        part_id="P1",
        track_index=0,
    )


def test_sixteenth_150bpm_zero_error():
    parsed = parse_score(FIXTURES / "sixteenth_150bpm.mid")
    result = quantize_beats(parsed.events, ticks_per_quarter=4)
    assert result.effective_bpm == 150
    assert result.stats.max_error_ms == 0
    assert result.stats.mean_error_ms == 0
    assert result.stats.moved_notes == 0
    assert result.stats.merged_notes == 0
    # 16分音符が 1 tick 刻みで並ぶ
    assert [q.tick for q in result.events] == list(range(16))


def test_rounding_error_stats():
    # offset 0.1 ql × tpq4 = 0.4 tick → tick 0、誤差 0.4 tick = 40ms
    result = quantize_beats([_event(0.0), _event(0.1, midi=62)], ticks_per_quarter=4)
    assert [q.tick for q in result.events] == [0, 0]
    assert result.stats.moved_notes == 1
    assert abs(result.stats.max_error_ms - 40.0) < 1e-9
    assert abs(result.stats.mean_error_ms - 20.0) < 1e-9


def test_dedupe_same_tick_same_pitch():
    # 同 tick に同じ音が2つ → 1つにマージ + 警告
    result = quantize_beats([_event(0.0), _event(0.05)], ticks_per_quarter=4)
    assert len(result.events) == 1
    assert result.stats.merged_notes == 1
    assert len(result.warnings) == 1
    assert result.warnings[0].type == "merge"


def test_same_tick_different_pitch_not_merged():
    result = quantize_beats([_event(0.0, midi=60), _event(0.0, midi=64)], ticks_per_quarter=4)
    assert len(result.events) == 2
    assert result.stats.merged_notes == 0


def test_effective_bpm_table():
    # RESEARCH.md §3: tpq 3|4|5|6|8 → 200|150|120|100|75 BPM
    for tpq, bpm in [(3, 200), (4, 150), (5, 120), (6, 100), (8, 75)]:
        result = quantize_beats([_event(0.0)], ticks_per_quarter=tpq)
        assert result.effective_bpm == bpm


def test_recommend_tpq():
    assert recommend_tpq(200) == 3
    assert recommend_tpq(150) == 4
    assert recommend_tpq(120) == 5
    assert recommend_tpq(100) == 6
    assert recommend_tpq(75) == 8
    assert recommend_tpq(90) == 6  # |100-90| < |75-90|
    assert recommend_tpq(135) == 4  # 同距離(150/120)は実効 BPM が高い方


def test_scale_c_major_quarter_notes():
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml")
    result = quantize_beats(parsed.events, ticks_per_quarter=4)
    # 4分音符 = 4 tick 刻み
    assert [q.tick for q in result.events] == [i * 4 for i in range(8)]
    assert result.stats.max_error_ms == 0
