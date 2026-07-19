"""quantizer(拍グリッド)の完了条件: sixteenth_150bpm.mid + tpq=4 で全ノート誤差 0。"""

from pathlib import Path

import pytest

from app.models.events import NoteEvent
from app.services.parser import parse_score
from app.services.quantizer import quantize_beats, quantize_seconds, recommend_tpq

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
    # マージされた音(0.05ql → 0.2 tick = 20ms 移動)も誤差統計に含まれる
    assert result.stats.moved_notes == 1
    assert abs(result.stats.max_error_ms - 20.0) < 1e-9


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


def test_90bpm_song_recommendation_and_error_stats():
    # 90BPM 曲 → 推奨 tpq は 6(実効 100BPM。|100-90| < |75-90|)
    assert recommend_tpq(90) == 6
    # 推奨 tpq6 では 8分3連(1/3 ql 刻み)が誤差ゼロでグリッドに乗る
    triplets = [_event(i / 3, midi=60 + i) for i in range(6)]
    result = quantize_beats(triplets, ticks_per_quarter=6)
    assert [q.tick for q in result.events] == [0, 2, 4, 6, 8, 10]
    assert result.stats.max_error_ms < 1e-9
    assert result.stats.moved_notes == 0

    # 16分(0.25 ql)は tpq6 のグリッドに乗らず、誤差統計に正確に反映される
    events = [
        _event(0.0),
        _event(0.25, midi=62),  # raw 1.5 tick → 2 に移動(誤差 0.5 tick = 50ms)
        _event(0.5, midi=64),
        _event(1.0, midi=65),
    ]
    result = quantize_beats(events, ticks_per_quarter=6)
    assert [q.tick for q in result.events] == [0, 2, 3, 6]
    assert result.stats.max_error_ms == 50.0
    assert result.stats.mean_error_ms == 12.5
    assert result.stats.moved_notes == 1


def test_tempo_change_seconds_mode():
    # 完了条件: tempo_change.mid が seconds モードで変換できる
    parsed = parse_score(FIXTURES / "tempo_change.mid")
    assert parsed.summary.has_tempo_changes
    result = quantize_seconds(parsed.events)
    # 120BPM 区間は 0.5s(=5 tick)刻み、90BPM 区間は 2/3s(≒6.67 tick)刻み
    assert [q.tick for q in result.events] == [0, 5, 10, 15, 20, 27, 33, 40]
    assert result.effective_bpm is None
    # 90BPM 区間の丸め誤差は最大 1/3 tick ≒ 33.3ms
    assert abs(result.stats.max_error_ms - 100 / 3) < 1e-6


def test_tempo_change_beat_mode_warns_flattening():
    # 完了条件: beat モードでは平坦化警告が付く
    parsed = parse_score(FIXTURES / "tempo_change.mid")
    result = quantize_beats(
        parsed.events, ticks_per_quarter=4, has_tempo_changes=parsed.summary.has_tempo_changes
    )
    assert any(w.type == "tempo_change" for w in result.warnings)
    # テンポ変化がない曲では警告なし
    scale = parse_score(FIXTURES / "scale_c_major.musicxml")
    assert not scale.summary.has_tempo_changes
    result2 = quantize_beats(
        scale.events, ticks_per_quarter=4, has_tempo_changes=scale.summary.has_tempo_changes
    )
    assert not any(w.type == "tempo_change" for w in result2.warnings)


def test_seconds_mode_tempo_scale():
    parsed = parse_score(FIXTURES / "tempo_change.mid")
    result = quantize_seconds(parsed.events, tempo_scale=2.0)
    assert [q.tick for q in result.events] == [0, 10, 20, 30, 40, 53, 67, 80]


def test_seconds_mode_requires_offset_seconds():
    event = NoteEvent(
        offset_ql=0.0, duration_ql=1.0, midi_pitch=60, part_id="P1", track_index=0
    )
    with pytest.raises(ValueError):
        quantize_seconds([event])


def test_scale_c_major_quarter_notes():
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml")
    result = quantize_beats(parsed.events, ticks_per_quarter=4)
    # 4分音符 = 4 tick 刻み
    assert [q.tick for q in result.events] == [i * 4 for i in range(8)]
    assert result.stats.max_error_ms == 0
