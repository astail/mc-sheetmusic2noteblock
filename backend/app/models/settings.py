"""変換リクエスト ConversionSettings(docs/DESIGN.md §7)。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversionSettings(BaseModel):
    mode: Literal["beat", "seconds"] = "beat"
    ticks_per_quarter: Literal[3, 4, 5, 6, 8] = 4  # 実効BPM 200|150|120|100|75
    tempo_scale: float = Field(default=1.0, gt=0)  # seconds モード用の倍率
    instrument_preset: Literal["bass_harp_bell", "harp_only", "custom"] = "bass_harp_bell"
    custom_ranges: Any = None  # custom プリセット用(形は P5 issue #46 で確定)
    transpose_semitones: int = 0
    hand_assignment: dict[str, Literal["right", "left", "ignore"]] | None = None
    measure_range: tuple[int, int] | None = None  # [開始小節, 終了小節] 部分変換
