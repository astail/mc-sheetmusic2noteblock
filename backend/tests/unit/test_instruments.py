"""docs/RESEARCH.md §1 の音色テーブルの検証。"""

from app.services.instruments import INSTRUMENTS

EXPECTED_RANGES = {
    "bass": (30, 54),
    "didgeridoo": (30, 54),
    "guitar": (42, 66),
    "harp": (54, 78),
    "iron_xylophone": (54, 78),
    "pling": (54, 78),
    "bit": (54, 78),
    "banjo": (54, 78),
    "cow_bell": (66, 90),
    "flute": (66, 90),
    "bell": (78, 102),
    "chime": (78, 102),
    "xylophone": (78, 102),
}
PERCUSSION = {"basedrum", "snare", "hat"}


def test_all_16_instruments_defined():
    assert set(INSTRUMENTS) == set(EXPECTED_RANGES) | PERCUSSION
    assert len(INSTRUMENTS) == 16


def test_melodic_ranges_match_research():
    for name, (base, top) in EXPECTED_RANGES.items():
        inst = INSTRUMENTS[name]
        assert not inst.is_percussion
        assert inst.base_midi == base
        assert inst.max_midi == top
        assert inst.max_midi == inst.base_midi + 24  # 25音(2オクターブ)


def test_percussion_has_no_range():
    for name in PERCUSSION:
        inst = INSTRUMENTS[name]
        assert inst.is_percussion
        assert inst.base_midi is None
        assert inst.max_midi is None


def test_clicks_calculation_example():
    # RESEARCH.md §1: C4 (MIDI 60) を harp (基準 F#3 = MIDI 54) で鳴らす → 6 クリック
    harp = INSTRUMENTS["harp"]
    assert 60 - harp.base_midi == 6


def test_base_blocks_match_design_example():
    # DESIGN.md §7 の Blueprint 例と同じブロック/日本語名
    assert INSTRUMENTS["harp"].base_block == "dirt"
    assert INSTRUMENTS["harp"].base_block_ja == "土(デフォルト系)"
    assert INSTRUMENTS["harp"].instrument_ja == "ハープ"
    assert INSTRUMENTS["bass"].base_block == "oak_planks"
    assert INSTRUMENTS["bass"].base_block_ja == "オークの板材"
    assert INSTRUMENTS["bass"].instrument_ja == "ベース"
    assert INSTRUMENTS["bell"].base_block == "gold_block"
