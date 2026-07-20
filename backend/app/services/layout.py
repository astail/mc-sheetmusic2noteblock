"""「直線リピーターバス + 櫛形分岐」の標準構成を Blueprint の layout として生成する(DESIGN.md §6・§7)。"""

from app.models.blueprint import Layout, LayoutSegment, Step
from app.services.blueprint_builder import BIG_CHORD_THRESHOLD

LAYOUT_TYPE = "comb_bus"
LAYOUT_DESCRIPTION = (
    "リピーターを +X 方向に直列。各ステップ位置から ±Z 方向へダスト分岐し音符ブロックを設置"
)


def build_layout(steps: list[Step]) -> Layout:
    segments: list[LayoutSegment] = []
    bus_offset = 0
    for step in steps:
        # バス上の物理位置(ブロック数)。リピーターは1〜4RTを1ブロックで表現するため
        # tick ではなくリピーター個数の累積で距離を数える
        bus_offset += step.repeaters.count
        # 同時発音数が多い(big_chord)ステップは片側の分岐だけでは音符ブロックが
        # 並びきらないため、両側(north/south)に分岐する
        branch_sides = ["north"] if len(step.notes) < BIG_CHORD_THRESHOLD else ["north", "south"]
        segments.append(
            LayoutSegment(
                step_index=step.index,
                bus_offset_blocks=bus_offset,
                branch_sides=branch_sides,
            )
        )
    return Layout(type=LAYOUT_TYPE, description=LAYOUT_DESCRIPTION, segments=segments)
