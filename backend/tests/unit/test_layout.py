"""layout.py の単体テスト: バス位置の累積計算と分岐方向の割当。"""

from app.models.blueprint import NotePlacement, Repeaters, Step
from app.services.layout import build_layout


def _note(hand="right") -> NotePlacement:
    return NotePlacement(
        instrument="harp",
        instrument_ja="ハープ",
        base_block="dirt",
        base_block_ja="土",
        clicks=6,
        note_name="C4",
        midi=60,
        hand=hand,
        octave_shift=0,
    )


def _step(index: int, tick: int, delay: int, chain: list[int], note_count: int = 1) -> Step:
    return Step(
        index=index,
        tick=tick,
        time_seconds=tick * 0.1,
        delay_from_prev_rticks=delay,
        repeaters=Repeaters(chain=chain, count=len(chain)),
        notes=[_note() for _ in range(note_count)],
    )


def test_bus_offset_accumulates_repeater_counts():
    steps = [
        _step(0, 0, 0, []),  # 先頭は delay=0 → リピーターなし
        _step(1, 7, 7, [4, 3]),  # +2個
        _step(2, 11, 4, [4]),  # +1個
    ]
    layout = build_layout(steps)
    assert [s.bus_offset_blocks for s in layout.segments] == [0, 2, 3]
    assert [s.step_index for s in layout.segments] == [0, 1, 2]


def test_branch_sides_single_for_small_chord():
    step = _step(0, 0, 0, [], note_count=4)  # big_chord 閾値未満
    layout = build_layout([step])
    assert layout.segments[0].branch_sides == ["north"]


def test_branch_sides_both_for_big_chord():
    step = _step(0, 0, 0, [], note_count=5)  # big_chord 閾値(5)以上
    layout = build_layout([step])
    assert layout.segments[0].branch_sides == ["north", "south"]


def test_layout_metadata():
    layout = build_layout([_step(0, 0, 0, [])])
    assert layout.type == "comb_bus"
    assert "リピーター" in layout.description
    assert "+X" in layout.description


def test_empty_steps():
    layout = build_layout([])
    assert layout.segments == []
