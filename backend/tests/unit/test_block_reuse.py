"""block_reuse の単体テスト: 配線距離による再利用可否とブロック番号の割当。"""

from app.models.blueprint import Layout, LayoutSegment, NotePlacement, Repeaters, Step
from app.services.block_reuse import (
    MAX_REUSE_DISTANCE_BLOCKS,
    assign_block_reuse,
    build_reuse_warning,
)

LAYOUT_TYPE = "comb_bus"
LAYOUT_DESCRIPTION = "test"


def _note(instrument="harp", clicks=6, hand="right") -> NotePlacement:
    return NotePlacement(
        instrument=instrument,
        instrument_ja=instrument,
        base_block="dirt",
        base_block_ja="土",
        clicks=clicks,
        note_name="C4",
        midi=60,
        hand=hand,
        octave_shift=0,
    )


def _step(index: int, notes: list[NotePlacement]) -> Step:
    return Step(
        index=index,
        tick=index,
        time_seconds=index * 0.1,
        delay_from_prev_rticks=0,
        repeaters=Repeaters(chain=[], count=0),
        notes=notes,
    )


def _layout(offsets: dict[int, int]) -> Layout:
    return Layout(
        type=LAYOUT_TYPE,
        description=LAYOUT_DESCRIPTION,
        segments=[
            LayoutSegment(step_index=i, bus_offset_blocks=o, branch_sides=["north"])
            for i, o in offsets.items()
        ],
    )


def test_reuses_within_wiring_distance():
    steps = [_step(0, [_note()]), _step(1, [_note()])]
    layout = _layout({0: 0, 1: MAX_REUSE_DISTANCE_BLOCKS})
    result = assign_block_reuse(steps, layout)
    first, second = result[0].notes[0], result[1].notes[0]
    assert first.block_id == second.block_id
    assert first.reused_from_step is None
    assert second.reused_from_step == 0


def test_does_not_reuse_beyond_wiring_distance():
    steps = [_step(0, [_note()]), _step(1, [_note()])]
    layout = _layout({0: 0, 1: MAX_REUSE_DISTANCE_BLOCKS + 1})
    result = assign_block_reuse(steps, layout)
    first, second = result[0].notes[0], result[1].notes[0]
    assert first.block_id != second.block_id
    assert second.reused_from_step is None


def test_different_instrument_or_clicks_never_reuses():
    steps = [
        _step(0, [_note(instrument="harp", clicks=6)]),
        _step(1, [_note(instrument="bell", clicks=6)]),
        _step(2, [_note(instrument="harp", clicks=7)]),
    ]
    layout = _layout({0: 0, 1: 1, 2: 2})
    result = assign_block_reuse(steps, layout)
    block_ids = [result[i].notes[0].block_id for i in range(3)]
    assert len(set(block_ids)) == 3


def test_rebases_origin_after_starting_a_new_block():
    # 1本目(offset0)と2本目(offset20)は遠すぎて再利用されず、2本目が新しい
    # 起点になる。3本目(offset25)は1本目からは遠いが2本目(起点)からは近いため
    # 2本目のブロックを再利用する
    steps = [_step(0, [_note()]), _step(1, [_note()]), _step(2, [_note()])]
    layout = _layout({0: 0, 1: 20, 2: 25})
    result = assign_block_reuse(steps, layout)
    first, second, third = (result[i].notes[0] for i in range(3))
    assert first.block_id != second.block_id
    assert third.block_id == second.block_id
    assert third.reused_from_step == 1


def test_percussion_notes_can_reuse():
    steps = [
        _step(0, [_note(instrument="basedrum", clicks=0, hand="percussion")]),
        _step(1, [_note(instrument="basedrum", clicks=0, hand="percussion")]),
    ]
    layout = _layout({0: 0, 1: 1})
    result = assign_block_reuse(steps, layout)
    assert result[0].notes[0].block_id == result[1].notes[0].block_id


def test_multiple_notes_in_a_chord_get_independent_block_ids():
    steps = [_step(0, [_note(instrument="harp", clicks=6), _note(instrument="bass", clicks=3)])]
    layout = _layout({0: 0})
    result = assign_block_reuse(steps, layout)
    harp_note, bass_note = result[0].notes
    assert harp_note.block_id != bass_note.block_id


def test_build_reuse_warning_none_when_no_reuse():
    steps = [_step(0, [_note(instrument="harp", clicks=6)]), _step(1, [_note(instrument="bass", clicks=3)])]
    layout = _layout({0: 0, 1: 1})
    result = assign_block_reuse(steps, layout)
    assert build_reuse_warning(result) is None


def test_build_reuse_warning_lists_reusing_steps():
    steps = [_step(0, [_note()]), _step(1, [_note()])]
    layout = _layout({0: 0, 1: 1})
    result = assign_block_reuse(steps, layout)
    warning = build_reuse_warning(result)
    assert warning is not None
    assert warning.type == "block_reuse"
    assert warning.steps == [1]  # 再利用側(reused_from_step が設定された)ステップのみ
    assert "本線バス" in warning.message
    assert "誤発火" in warning.message
