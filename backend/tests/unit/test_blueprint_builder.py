"""blueprint_builder の完了条件: delay 分解と Step 列の数値が単体テストで一致。"""

from pathlib import Path

from app import config
from app.models.blueprint import Blueprint, Materials
from app.models.events import NoteEvent
from app.services.blueprint_builder import (
    build_blueprint_parts,
    decompose_delay,
    note_name,
)
from app.services.hand_split import split_hands
from app.services.parser import parse_score
from app.services.quantizer import QuantizedEvent, quantize_beats

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _qe(tick: int, midi: int = 60, channel: int | None = None) -> QuantizedEvent:
    return QuantizedEvent(
        event=NoteEvent(
            offset_ql=tick / 4,
            duration_ql=1.0,
            midi_pitch=midi,
            part_id="P1",
            track_index=0,
            channel=channel,
        ),
        tick=tick,
    )


def _build(quantized, hands, **overrides):
    from app.models.blueprint import QuantizationStats

    kwargs = dict(
        title="test",
        source_file="test.mid",
        original_bpm=150.0,
        ticks_per_quarter=4,
        effective_bpm=150.0,
        quantization_stats=QuantizationStats(
            max_error_ms=0, mean_error_ms=0, moved_notes=0, merged_notes=0
        ),
    )
    kwargs.update(overrides)
    return build_blueprint_parts(quantized, hands, **kwargs)


def test_decompose_delay():
    # issue #15 の例: 7→[4,3]、12→[4,4,4]
    assert decompose_delay(7) == [4, 3]
    assert decompose_delay(12) == [4, 4, 4]
    assert decompose_delay(0) == []
    # 1〜4 は単一リピーター
    for d in (1, 2, 3, 4):
        assert decompose_delay(d) == [d]
    assert decompose_delay(5) == [4, 1]


def test_step_sequence_numbers():
    quantized = [_qe(0), _qe(4, midi=62), _qe(11, midi=64)]
    meta, steps, warnings = _build(quantized, ["right"] * 3)
    assert [s.index for s in steps] == [0, 1, 2]
    assert [s.tick for s in steps] == [0, 4, 11]
    assert [s.delay_from_prev_rticks for s in steps] == [0, 4, 7]
    assert [s.repeaters.chain for s in steps] == [[], [4], [4, 3]]
    assert [s.time_seconds for s in steps] == [0.0, 0.4, 1.1]
    assert meta.total_rticks == 11
    assert meta.duration_seconds == 1.1
    assert meta.step_count == 3


def test_first_step_with_nonzero_tick():
    # 先頭ステップは曲頭(tick 0)からの遅延として扱う
    meta, steps, _ = _build([_qe(3)], ["right"])
    assert steps[0].delay_from_prev_rticks == 3
    assert steps[0].repeaters.chain == [3]


def test_chord_grouped_into_one_step():
    quantized = [_qe(0, midi=60), _qe(0, midi=64), _qe(0, midi=67)]
    _, steps, warnings = _build(quantized, ["right"] * 3)
    assert len(steps) == 1
    assert len(steps[0].notes) == 3
    assert not any(w.type == "big_chord" for w in warnings)


def test_other_hand_excluded():
    quantized = [_qe(0, midi=60), _qe(0, midi=64)]
    _, steps, _ = _build(quantized, ["right", "other"])
    assert len(steps[0].notes) == 1


def test_big_chord_warning():
    quantized = [_qe(0, midi=m) for m in (60, 62, 64, 65, 67)]  # 同時5音
    _, steps, warnings = _build(quantized, ["right"] * 5)
    big = [w for w in warnings if w.type == "big_chord"]
    assert len(big) == 1
    assert big[0].steps == [0]
    assert "同時5音" in big[0].message
    assert "分岐ダストを南北（±Z）の両側に伸ばし" in big[0].message


def test_repeater_limit_warning_uses_config_threshold(monkeypatch):
    monkeypatch.setattr(config, "REPEATER_WARNING_THRESHOLD", 1)
    quantized = [_qe(0), _qe(4, midi=62), _qe(8, midi=64)]
    _, steps, warnings = _build(quantized, ["right"] * 3)
    assert sum(step.repeaters.count for step in steps) == 2
    warning = [w for w in warnings if w.type == "repeater_limit"]
    assert len(warning) == 1
    assert warning[0].steps is None
    assert "リピーター総数は2個" in warning[0].message
    assert "設定閾値の1個" in warning[0].message
    assert "曲を分割して複数の演奏装置に" in warning[0].message


def test_repeater_limit_warning_not_added_at_threshold(monkeypatch):
    monkeypatch.setattr(config, "REPEATER_WARNING_THRESHOLD", 2)
    quantized = [_qe(0), _qe(4, midi=62), _qe(8, midi=64)]
    _, _, warnings = _build(quantized, ["right"] * 3)
    assert not any(w.type == "repeater_limit" for w in warnings)


def test_octave_shift_warning_has_step_indices():
    quantized = [_qe(0, midi=21), _qe(4, midi=60)]  # A0 はシフト対象
    _, steps, warnings = _build(quantized, ["left", "right"])
    shift = [w for w in warnings if w.type == "octave_shift"]
    assert len(shift) == 1
    assert shift[0].steps == [0]
    # シフト後の実効値が NotePlacement に反映される
    placed = steps[0].notes[0]
    assert placed.midi == 33
    assert placed.octave_shift == 1


def test_mapped_note_collision_deduped():
    # MIDI 21 は +1 オクターブで 33 になり、素の 33 と同一の (bass, 3クリック) に衝突する
    quantized = [_qe(0, midi=21), _qe(0, midi=33)]
    _, steps, warnings = _build(quantized, ["left", "left"])
    assert len(steps[0].notes) == 1
    assert (steps[0].notes[0].instrument, steps[0].notes[0].clicks) == ("bass", 3)
    merge = [w for w in warnings if w.type == "merge"]
    assert len(merge) == 1
    assert merge[0].steps == [0]


def test_note_name():
    assert note_name(60) == "C4"
    assert note_name(54) == "F#3"


def test_percussion_note_has_no_pitch_and_fixed_clicks():
    quantized = [_qe(0, midi=36, channel=10)]  # bass drum
    _, steps, _ = _build(quantized, ["percussion"])
    placed = steps[0].notes[0]
    assert placed.instrument == "basedrum"
    assert placed.clicks == 0
    assert placed.midi is None
    assert placed.note_name is None
    assert placed.hand == "percussion"


def test_percussion_and_melodic_notes_coexist_in_same_step():
    quantized = [_qe(0, midi=60), _qe(0, midi=38, channel=10)]  # harp + snare
    _, steps, _ = _build(quantized, ["right", "percussion"])
    assert len(steps) == 1
    instruments = {n.instrument for n in steps[0].notes}
    assert instruments == {"harp", "snare"}
    assert note_name(21) == "A0"
    assert note_name(108) == "C8"


def test_scale_fixture_end_to_end_numbers():
    # IMPLEMENTATION_PLAN の E2E 数値: steps 8、delay 4(先頭は 0)、全音 harp、C4 = 6クリック
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml")
    result = quantize_beats(parsed.events, ticks_per_quarter=4)
    # quantizer は並べ替えるため hands は量子化後のイベント順で作る
    hands = split_hands([q.event for q in result.events])
    meta, steps, warnings = _build(
        result.events,
        hands,
        title="scale",
        source_file="scale_c_major.musicxml",
        original_bpm=120.0,
        quantization_stats=result.stats,
    )
    assert meta.step_count == 8
    assert [s.delay_from_prev_rticks for s in steps] == [0] + [4] * 7
    assert all(n.instrument == "harp" for s in steps for n in s.notes)
    assert steps[0].notes[0].clicks == 6  # C4
    assert warnings == []


def test_assembled_blueprint_validates():
    # 生成した Step 列が Blueprint モデルの整合検証(tick/delay/repeaters)を通る
    parsed = parse_score(FIXTURES / "twinkle_both_hands.musicxml")
    result = quantize_beats(parsed.events, ticks_per_quarter=4)
    hands = split_hands([q.event for q in result.events])
    meta, steps, warnings = _build(
        result.events,
        hands,
        title="twinkle",
        source_file="twinkle_both_hands.musicxml",
        original_bpm=100.0,
        quantization_stats=result.stats,
    )
    blueprint = Blueprint(
        meta=meta,
        steps=steps,
        materials=Materials(
            note_block=0, repeater=0, redstone_dust_estimate=0, base_blocks={}, notes=[]
        ),
        warnings=warnings,
    )
    assert blueprint.meta.step_count == len(blueprint.steps)
    # 手の対応が量子化の並べ替え後も正しい(右手=メロディ14音、左手=和音12音)
    placed = [n for s in blueprint.steps for n in s.notes]
    assert sum(1 for n in placed if n.hand == "right") == 14
    assert sum(1 for n in placed if n.hand == "left") == 12
    # staff 1(右手)は 4 オクターブ帯、staff 2(左手)は低域という元データの性質も保たれる
    assert all(n.midi >= 60 for n in placed if n.hand == "right")
    assert all(n.midi < 60 for n in placed if n.hand == "left")


def test_meta_without_original_bpm():
    # テンポ記号がない楽譜(summary.original_bpm=None)でも meta が組み立てられる
    meta, _, _ = _build([_qe(0)], ["right"], original_bpm=None)
    assert meta.original_bpm is None


def test_seconds_mode_meta_without_bpm():
    # seconds モード(effective_bpm / tpq なし)でも meta が組み立てられる
    meta, steps, _ = _build(
        [_qe(0)],
        ["right"],
        ticks_per_quarter=None,
        effective_bpm=None,
    )
    assert meta.effective_bpm is None
    assert meta.ticks_per_quarter is None
    assert meta.step_count == 1
