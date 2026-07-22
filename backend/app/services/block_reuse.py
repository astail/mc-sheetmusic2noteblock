"""同一(音色, クリック数)の音符ブロックを再利用できるか判定する(Phase 5 issue #45)。

再利用条件:
- 同一ステップ内の重複は blueprint_builder が既にマージ済みのため対象外
- 配線距離: レッドストーンダストは中継(リピーター)無しでは15ブロックまでしか
  信号が届かない。bus_offset_blocks の差はバス上(X方向)の距離のみで、実際の
  ブロックはそこから ±Z 方向の分岐(branch)上に離れて置かれているため、
  再利用の配線はバス方向の距離に加えて分岐方向の距離も消費する。layout は
  ステップ単位の分岐方向(north/south)のみを持ち個々のブロックの分岐上の
  深さまでは追跡していないため、正確な残り距離は計算できない。分岐の深さ
  (大和音でも片側最大 BIG_CHORD_THRESHOLD 個程度を想定)とバスをまたぐ迂回分の
  余裕として BRANCH_RESERVE_BLOCKS を差し引いた値をバス方向距離の上限とする
  (非常に大きな和音では実際の配線距離がこの見積りを超える可能性が残る)
"""

from app.models.blueprint import Layout, Step

DUST_MAX_RANGE_BLOCKS = 15
BRANCH_RESERVE_BLOCKS = 5  # 分岐方向の深さ + バスをまたぐ迂回分の見積り
MAX_REUSE_DISTANCE_BLOCKS = DUST_MAX_RANGE_BLOCKS - BRANCH_RESERVE_BLOCKS


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
