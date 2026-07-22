"""materials の完了条件: 単体テストで集計値が一致。"""

from pathlib import Path

from app.models.blueprint import NotePlacement, QuantizationStats, Repeaters, Step
from app.services.blueprint_builder import build_blueprint_parts
from app.services.hand_split import split_hands
from app.services.materials import count_materials
from app.services.parser import parse_score
from app.services.quantizer import quantize_beats

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _steps(fixture: str, original_bpm: float):
    parsed = parse_score(FIXTURES / fixture)
    result = quantize_beats(parsed.events, ticks_per_quarter=4)
    hands = split_hands([q.event for q in result.events])
    _, steps, _ = build_blueprint_parts(
        result.events,
        hands,
        title="t",
        source_file=fixture,
        original_bpm=original_bpm,
        ticks_per_quarter=4,
        effective_bpm=150.0,
        quantization_stats=result.stats,
    )
    return steps


def test_scale_c_major_counts():
    steps = _steps("scale_c_major.musicxml", 120.0)
    materials = count_materials(steps)
    assert materials.note_block == 8  # ドレミ8音 = 8ブロック
    assert materials.repeater == 7  # 先頭 delay0 + 4tick 刻み×7(各[4]=1個)
    assert materials.redstone_dust_estimate == 16  # 8ステップ × 2
    assert materials.base_blocks == {"dirt": 8}  # 全音 harp
    assert "音符ブロックの真上は空気にすること" in materials.notes
    assert "起動用ボタン/レバー 1個" in materials.notes


def test_twinkle_counts_match_steps():
    steps = _steps("twinkle_both_hands.musicxml", 100.0)
    materials = count_materials(steps)
    # 右手14音 + 左手和音12音(マージ・除外なし)
    assert materials.note_block == 26
    assert materials.note_block == sum(len(s.notes) for s in steps)
    assert materials.repeater == sum(s.repeaters.count for s in steps)
    assert materials.redstone_dust_estimate == len(steps) * 2
    # 右手14音は harp(dirt)。左手和音は G3(55)×3 が harp 域、残り9音が bass(oak_planks)
    assert materials.base_blocks == {"dirt": 17, "oak_planks": 9}


def test_empty_steps():
    materials = count_materials([])
    assert materials.note_block == 0
    assert materials.repeater == 0
    assert materials.redstone_dust_estimate == 0
    assert materials.base_blocks == {}


def _note_with_block(block_id: int, instrument="harp", base_block="dirt") -> NotePlacement:
    return NotePlacement(
        instrument=instrument,
        instrument_ja=instrument,
        base_block=base_block,
        base_block_ja=base_block,
        clicks=6,
        note_name="C4",
        midi=60,
        hand="right",
        octave_shift=0,
        block_id=block_id,
    )


def _step_with_notes(index: int, notes: list[NotePlacement]) -> Step:
    return Step(
        index=index,
        tick=index,
        time_seconds=index * 0.1,
        delay_from_prev_rticks=0,
        repeaters=Repeaters(chain=[], count=0),
        notes=notes,
    )


def test_reused_blocks_are_counted_once():
    # block_id=1 が2回、block_id=2 が1回 → 実際に必要なブロックは2個
    steps = [
        _step_with_notes(0, [_note_with_block(1)]),
        _step_with_notes(1, [_note_with_block(1)]),
        _step_with_notes(2, [_note_with_block(2, base_block="oak_planks")]),
    ]
    materials = count_materials(steps)
    assert materials.note_block == 2
    assert materials.base_blocks == {"dirt": 1, "oak_planks": 1}
    assert any("再利用" in note and "1箇所" in note for note in materials.notes)


def test_no_reuse_note_when_all_blocks_are_unique():
    steps = [
        _step_with_notes(0, [_note_with_block(1)]),
        _step_with_notes(1, [_note_with_block(2)]),
    ]
    materials = count_materials(steps)
    assert materials.note_block == 2
    assert not any("再利用" in note for note in materials.notes)
