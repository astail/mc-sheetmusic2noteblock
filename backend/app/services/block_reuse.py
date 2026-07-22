"""同一(音色, クリック数)の音符ブロックを再利用できるか判定する(Phase 5 issue #45)。

再利用条件:
- 同一ステップ内の重複は blueprint_builder が既にマージ済みのため対象外
- 配線距離: レッドストーンダストは中継(リピーター)無しでは15ブロックまでしか
  信号が届かないため、ブロックの物理的な設置位置(layout.bus_offset_blocks)から
  15ブロックを超える場所では新しいブロックを置き直す方が単純
"""

from app.models.blueprint import Layout, Step

MAX_REUSE_DISTANCE_BLOCKS = 15


def assign_block_reuse(steps: list[Step], layout: Layout) -> list[Step]:
    bus_offset_by_step = {seg.step_index: seg.bus_offset_blocks for seg in layout.segments}
    # (instrument, clicks) → そのブロックが実際に置かれている (block_id, origin_step, origin_offset)
    origin_by_key: dict[tuple[str, int], tuple[int, int, int]] = {}
    next_block_id = 1

    new_steps: list[Step] = []
    for step in steps:
        offset = bus_offset_by_step.get(step.index, 0)
        new_notes = []
        for note in step.notes:
            key = (note.instrument, note.clicks)
            origin = origin_by_key.get(key)
            if origin is not None and abs(offset - origin[2]) <= MAX_REUSE_DISTANCE_BLOCKS:
                block_id, origin_step, _ = origin
                new_notes.append(
                    note.model_copy(
                        update={"block_id": block_id, "reused_from_step": origin_step}
                    )
                )
            else:
                block_id = next_block_id
                next_block_id += 1
                origin_by_key[key] = (block_id, step.index, offset)
                new_notes.append(
                    note.model_copy(update={"block_id": block_id, "reused_from_step": None})
                )
        new_steps.append(step.model_copy(update={"notes": new_notes}))
    return new_steps
