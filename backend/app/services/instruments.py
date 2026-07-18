"""音色(instrument)ごとの音域・下に置くブロック・日本語名の静的テーブル。

docs/RESEARCH.md §1 の16音色。0 クリック = 基準音、24 クリック = 基準音 + 2 オクターブ。
clicks = midi - base_midi で計算する(例: C4=60 を harp(基準 F#3=54)で鳴らす → 6 クリック)。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    name: str
    instrument_ja: str
    base_block: str
    base_block_ja: str
    base_midi: int | None  # 0 クリックの MIDI 番号。打楽器は None
    max_midi: int | None  # base_midi + 24。打楽器は None
    is_percussion: bool = False


def _melodic(name: str, ja: str, block: str, block_ja: str, base: int) -> Instrument:
    return Instrument(name, ja, block, block_ja, base, base + 24)


def _percussion(name: str, ja: str, block: str, block_ja: str) -> Instrument:
    return Instrument(name, ja, block, block_ja, None, None, is_percussion=True)


INSTRUMENTS: dict[str, Instrument] = {
    inst.name: inst
    for inst in [
        # 低音 F#1〜F#3 (30〜54)
        _melodic("bass", "ベース", "oak_planks", "オークの板材", 30),
        _melodic("didgeridoo", "ディジュリドゥ", "pumpkin", "パンプキン", 30),
        # 中低音 F#2〜F#4 (42〜66)
        _melodic("guitar", "ギター", "white_wool", "羊毛(白)", 42),
        # 中音 F#3〜F#5 (54〜78)
        _melodic("harp", "ハープ", "dirt", "土(デフォルト系)", 54),
        _melodic("iron_xylophone", "鉄琴", "iron_block", "鉄ブロック", 54),
        _melodic("pling", "プリング", "glowstone", "グロウストーン", 54),
        _melodic("bit", "ビット", "emerald_block", "エメラルドブロック", 54),
        _melodic("banjo", "バンジョー", "hay_block", "干草の俵", 54),
        # 中高音 F#4〜F#6 (66〜90)
        _melodic("cow_bell", "カウベル", "soul_sand", "ソウルサンド", 66),
        _melodic("flute", "フルート", "clay", "粘土", 66),
        # 高音 F#5〜F#7 (78〜102)
        _melodic("bell", "ベル", "gold_block", "金ブロック", 78),
        _melodic("chime", "チャイム", "packed_ice", "パックドアイス", 78),
        _melodic("xylophone", "木琴", "bone_block", "骨ブロック", 78),
        # 打楽器(音域なし。Phase 5 issue #44 で使用)
        _percussion("basedrum", "バスドラム", "stone", "石"),
        _percussion("snare", "スネア", "sand", "砂"),
        _percussion("hat", "ハット", "glass", "ガラス"),
    ]
}
