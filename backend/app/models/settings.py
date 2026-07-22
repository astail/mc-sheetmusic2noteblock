"""変換リクエスト ConversionSettings(docs/DESIGN.md §7)。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CustomRange(BaseModel):
    """instrument_preset="custom" 用の音色レンジ1件。range_start_midi はこの音色を
    使い始める元曲側のMIDI番号(境界)。音色自体の物理的な基準音(clicks=0の実際の
    音高)は instruments.py の base_midi で固定されており、range_start_midi では
    変更できない(pitch_mapper.map_custom がその音色自身のレンジへ改めて収める)。"""

    model_config = ConfigDict(extra="forbid")

    instrument: str
    range_start_midi: int


class ConversionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 未知キー(綴り間違い等)を 422 で弾く

    mode: Literal["beat", "seconds"] = "beat"
    ticks_per_quarter: Literal[3, 4, 5, 6, 8] = 4  # 実効BPM 200|150|120|100|75
    tempo_scale: float = Field(default=1.0, gt=0, allow_inf_nan=False)  # seconds モード用の倍率
    instrument_preset: Literal["bass_harp_bell", "harp_only", "custom"] = "bass_harp_bell"
    custom_ranges: list[CustomRange] | None = None  # custom プリセット用
    transpose_semitones: int = 0
    hand_assignment: dict[str, Literal["right", "left", "ignore"]] | None = None
    measure_range: tuple[int, int] | None = None  # [開始小節, 終了小節] 部分変換

    @field_validator("measure_range")
    @classmethod
    def _measure_range_ordered(cls, v: tuple[int, int] | None) -> tuple[int, int] | None:
        if v is not None:
            start, end = v
            if start < 1 or start > end:
                raise ValueError("measure_range は 1 以上かつ 開始 <= 終了 であること")
        return v

    @model_validator(mode="after")
    def _custom_ranges_required_for_custom_preset(self) -> "ConversionSettings":
        if self.instrument_preset == "custom" and not self.custom_ranges:
            raise ValueError("instrument_preset='custom' には custom_ranges の指定が必要です")
        return self
