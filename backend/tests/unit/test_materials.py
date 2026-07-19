"""materials の完了条件: 単体テストで集計値が一致。"""

from pathlib import Path

from app.models.blueprint import QuantizationStats
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
