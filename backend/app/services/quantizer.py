"""拍グリッド量子化(既定モード。docs/RESEARCH.md §3、DESIGN.md §6)。

offset_ql(quarterLength)× ticks_per_quarter を最近傍丸めして整数 tick(RT)を割り当てる。
実効 BPM = 600 / tpq。丸め誤差は拍位置に対して一定比率でドリフトしない。
"""

import math

from pydantic import BaseModel

from app.models.blueprint import QuantizationStats, Warning
from app.models.events import NoteEvent

TICK_MS = 100.0  # 1 RT = 0.1 秒
ALLOWED_TPQ = (3, 4, 5, 6, 8)
_ERROR_EPS_MS = 1e-6


class QuantizedEvent(BaseModel):
    event: NoteEvent
    tick: int


class QuantizationResult(BaseModel):
    events: list[QuantizedEvent]  # tick 昇順。同 tick・同音の重複はデデュープ済み
    effective_bpm: float
    stats: QuantizationStats
    warnings: list[Warning]


def effective_bpm(ticks_per_quarter: int) -> float:
    return 600.0 / ticks_per_quarter


def recommend_tpq(original_bpm: float) -> int:
    """原曲 BPM に実効 BPM が最も近い tpq を返す(同距離なら実効 BPM が高い方)。"""
    return min(ALLOWED_TPQ, key=lambda tpq: (abs(effective_bpm(tpq) - original_bpm), tpq))


def quantize_beats(events: list[NoteEvent], ticks_per_quarter: int) -> QuantizationResult:
    quantized: list[QuantizedEvent] = []
    errors_ms: list[float] = []
    seen: set[tuple[int, int]] = set()
    merged = 0

    for event in sorted(events, key=lambda e: (e.offset_ql, e.midi_pitch)):
        raw_tick = event.offset_ql * ticks_per_quarter
        tick = math.floor(raw_tick + 0.5)  # 最近傍丸め(0.5 は常に切り上げ)
        # 誤差統計はマージされる音も含め全入力ノートを対象にする
        errors_ms.append(abs(raw_tick - tick) * TICK_MS)
        key = (tick, event.midi_pitch)
        if key in seen:
            merged += 1
            continue
        seen.add(key)
        quantized.append(QuantizedEvent(event=event, tick=tick))

    moved = sum(1 for e in errors_ms if e > _ERROR_EPS_MS)
    stats = QuantizationStats(
        max_error_ms=max(errors_ms) if errors_ms else 0.0,
        mean_error_ms=sum(errors_ms) / len(errors_ms) if errors_ms else 0.0,
        moved_notes=moved,
        merged_notes=merged,
    )
    warnings: list[Warning] = []
    if merged:
        warnings.append(
            Warning(
                type="merge",
                message=f"同一 tick に落ちた同じ音 {merged} 音をマージしました",
            )
        )
    return QuantizationResult(
        events=quantized,
        effective_bpm=effective_bpm(ticks_per_quarter),
        stats=stats,
        warnings=warnings,
    )
