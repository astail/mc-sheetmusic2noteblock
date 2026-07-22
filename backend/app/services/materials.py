"""設計書ステップ列から必要資材を集計する(DESIGN.md §6・§7)。"""

from collections import Counter

from app.models.blueprint import Materials, Step
from app.services.block_reuse import MAX_REUSE_DISTANCE_BLOCKS

# 標準構成(櫛形バス)の概算: 各ステップから ±Z 方向の分岐に 1 本ずつ
DUST_PER_STEP = 2

# 再利用配線は本線バスに接触しない迂回路が必要(block_reuse.build_reuse_warning)。
# 配線距離の上限 + 別の層へ上下移動する分の概算をリピーター無しの1本あたりの
# 追加ダストとする(実際の距離は再利用ごとに異なるが、layout をここまで持ち込まず
# 上限ベースの概算に留める)
REUSE_DUST_RESERVE_BLOCKS = MAX_REUSE_DISTANCE_BLOCKS + 2

MATERIAL_NOTES = [
    "音符ブロックの真上は空気にすること",
    "起動用ボタン/レバー 1個",
]


def count_materials(steps: list[Step]) -> Materials:
    all_notes = [note for step in steps for note in step.notes]
    # block_id が付与されている(services/block_reuse.py 適用後の)場合のみ、
    # 同じ block_id の note は同一の物理ブロックとして1個にまとめる。
    # block_id が無い(未適用)場合は従来通り1音=1ブロックとして数える
    seen_block_ids: set[int] = set()
    unique_notes = []
    for note in all_notes:
        if note.block_id is not None:
            if note.block_id in seen_block_ids:
                continue
            seen_block_ids.add(note.block_id)
        unique_notes.append(note)
    reused_count = len(all_notes) - len(unique_notes)

    notes = list(MATERIAL_NOTES)
    if reused_count:
        notes.append(f"{reused_count}箇所で既存の音符ブロックを再利用し、資材を{reused_count}個削減しました")

    return Materials(
        note_block=len(unique_notes),
        repeater=sum(step.repeaters.count for step in steps),
        redstone_dust_estimate=len(steps) * DUST_PER_STEP
        + reused_count * REUSE_DUST_RESERVE_BLOCKS,
        base_blocks=dict(Counter(note.base_block for note in unique_notes)),
        notes=notes,
    )
