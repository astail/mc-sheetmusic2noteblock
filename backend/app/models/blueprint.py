"""設計書 Blueprint(レスポンス & 永続化。docs/DESIGN.md §7)。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class QuantizationStats(BaseModel):
    max_error_ms: float
    mean_error_ms: float
    moved_notes: int
    merged_notes: int


class Meta(BaseModel):
    title: str
    source_file: str
    original_bpm: float | None = None  # テンポ記号がない楽譜では None
    effective_bpm: float | None = None  # seconds モードでは None
    ticks_per_quarter: int | None = None  # seconds モードでは None
    total_rticks: int
    duration_seconds: float
    step_count: int
    quantization: QuantizationStats


class Repeaters(BaseModel):
    chain: list[Annotated[int, Field(ge=1, le=4)]]  # 各リピーターの目盛
    count: int

    @model_validator(mode="after")
    def _count_matches_chain(self) -> "Repeaters":
        if self.count != len(self.chain):
            raise ValueError("count は chain の要素数と一致すること")
        return self


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
    note_name: str | None = None  # 打楽器には音程の概念がないため None
    midi: int | None = None  # 打楽器には音程の概念がないため None
    hand: Literal["right", "left", "percussion"]
    octave_shift: int
    source: NoteSource | None = None


class Step(BaseModel):
    index: int
    tick: int
    time_seconds: float
    delay_from_prev_rticks: int
    repeaters: Repeaters
    notes: list[NotePlacement]

    @model_validator(mode="after")
    def _repeaters_match_delay(self) -> "Step":
        # 組み立てビューはリピーター分解、プレビュー再生は tick を使うため両者の整合を保証する
        if sum(self.repeaters.chain) != self.delay_from_prev_rticks:
            raise ValueError("repeaters.chain の合計は delay_from_prev_rticks と一致すること")
        return self


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

    @model_validator(mode="after")
    def _steps_tick_consistent(self) -> "Blueprint":
        # プレビュー再生(tick)と組み立てカード(delay)が同じタイミングになることを保証する
        for prev, cur in zip(self.steps, self.steps[1:]):
            if cur.tick <= prev.tick:
                raise ValueError("steps は tick 昇順であること")
            if cur.delay_from_prev_rticks != cur.tick - prev.tick:
                raise ValueError(
                    "delay_from_prev_rticks は直前ステップとの tick 差と一致すること"
                )
        return self
