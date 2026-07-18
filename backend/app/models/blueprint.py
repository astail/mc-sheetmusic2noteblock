"""設計書 Blueprint(レスポンス & 永続化。docs/DESIGN.md §7)。"""

from typing import Literal

from pydantic import BaseModel, Field


class QuantizationStats(BaseModel):
    max_error_ms: float
    mean_error_ms: float
    moved_notes: int
    merged_notes: int


class Meta(BaseModel):
    title: str
    source_file: str
    original_bpm: float
    effective_bpm: float
    ticks_per_quarter: int
    total_rticks: int
    duration_seconds: float
    step_count: int
    quantization: QuantizationStats


class Repeaters(BaseModel):
    chain: list[int]  # 各リピーターの目盛(1〜4)
    count: int


class NoteSource(BaseModel):
    measure: int
    beat: float
    part: str


class NotePlacement(BaseModel):
    instrument: str
    instrument_ja: str
    base_block: str
    base_block_ja: str
    clicks: int = Field(ge=0, le=24)
    note_name: str
    midi: int
    hand: Literal["right", "left"]
    octave_shift: int
    source: NoteSource | None = None


class Step(BaseModel):
    index: int
    tick: int
    time_seconds: float
    delay_from_prev_rticks: int
    repeaters: Repeaters
    notes: list[NotePlacement]


class Materials(BaseModel):
    note_block: int
    repeater: int
    redstone_dust_estimate: int
    base_blocks: dict[str, int]
    notes: list[str]


class Warning(BaseModel):
    type: str  # octave_shift | big_chord | tempo_change など
    message: str
    steps: list[int] | None = None


class LayoutSegment(BaseModel):
    step_index: int
    bus_offset_blocks: int
    branch_sides: list[str]


class Layout(BaseModel):
    type: str
    description: str
    segments: list[LayoutSegment]


class Blueprint(BaseModel):
    meta: Meta
    steps: list[Step]
    materials: Materials
    warnings: list[Warning]
    layout: Layout | None = None  # 物理レイアウト提案は Phase 3(issue #35)で生成
