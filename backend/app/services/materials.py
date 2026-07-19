"""設計書ステップ列から必要資材を集計する(DESIGN.md §6・§7)。"""

from collections import Counter

from app.models.blueprint import Materials, Step

# 標準構成(櫛形バス)の概算: 各ステップから ±Z 方向の分岐に 1 本ずつ
DUST_PER_STEP = 2

MATERIAL_NOTES = [
    "音符ブロックの真上は空気にすること",
    "起動用ボタン/レバー 1個",
]


def count_materials(steps: list[Step]) -> Materials:
    return Materials(
        note_block=sum(len(step.notes) for step in steps),
        repeater=sum(step.repeaters.count for step in steps),
        redstone_dust_estimate=len(steps) * DUST_PER_STEP,
        base_blocks=dict(
            Counter(note.base_block for step in steps for note in step.notes)
        ),
        notes=list(MATERIAL_NOTES),
    )
