"""量子化済みノート群から設計書のステップ列と meta を組み立てる(DESIGN.md §6・§7)。

- tick 昇順のユニーク集合 → Step 列。delay = tick_n − tick_{n−1}(先頭は曲頭 tick 0 からの遅延)
- リピーター分解: d → [4]×(d//4) + ([d%4] if d%4 else [])
- materials は services/materials.py(issue #16)、layout は issue #35 の責務
"""

from collections import defaultdict

from app.models.blueprint import (
    Meta,
    NotePlacement,
    NoteSource,
    QuantizationStats,
    Repeaters,
    Step,
    Warning,
)
from app.services.hand_split import Hand
from app.services.instruments import INSTRUMENTS
from app.services.pitch_mapper import map_pitch
from app.services.quantizer import QuantizedEvent

TICK_SECONDS = 0.1
# 同時発音がこの数以上の Step は big_chord 警告(配線ガイドの詳細は issue #39)
BIG_CHORD_THRESHOLD = 5

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def decompose_delay(delay: int) -> list[int]:
    """リピーター分解: 7 → [4, 3]、12 → [4, 4, 4]、0 → []。"""
    return [4] * (delay // 4) + ([delay % 4] if delay % 4 else [])


def build_blueprint_parts(
    quantized: list[QuantizedEvent],
    hands: list[Hand],
    *,
    title: str,
    source_file: str,
    original_bpm: float,
    ticks_per_quarter: int,
    effective_bpm: float,
    quantization_stats: QuantizationStats,
    preset: str = "bass_harp_bell",
    transpose_semitones: int = 0,
) -> tuple[Meta, list[Step], list[Warning]]:
    """Step 列・meta・警告(big_chord / octave_shift)を組み立てる。

    hands は quantized と同順。hand が "other" のイベントは設計書から除外する。
    """
    by_tick: dict[int, list[NotePlacement]] = defaultdict(list)
    shifted_notes = 0
    shift_amounts: list[int] = []
    for q, hand in zip(quantized, hands):
        if hand == "other":
            continue
        mapped = map_pitch(
            q.event.midi_pitch, preset=preset, transpose_semitones=transpose_semitones
        )
        inst = INSTRUMENTS[mapped.instrument]
        effective_midi = inst.base_midi + mapped.clicks
        source = None
        if q.event.measure is not None and q.event.beat is not None:
            source = NoteSource(
                measure=q.event.measure, beat=q.event.beat, part=q.event.part_id
            )
        if mapped.octave_shift != 0:
            shifted_notes += 1
            shift_amounts.append(mapped.octave_shift)
        by_tick[q.tick].append(
            NotePlacement(
                instrument=mapped.instrument,
                instrument_ja=inst.instrument_ja,
                base_block=inst.base_block,
                base_block_ja=inst.base_block_ja,
                clicks=mapped.clicks,
                note_name=note_name(effective_midi),
                midi=effective_midi,
                hand=hand,
                octave_shift=mapped.octave_shift,
                source=source,
            )
        )

    steps: list[Step] = []
    big_chord_steps: list[int] = []
    octave_shift_steps: list[int] = []
    prev_tick = 0
    for index, tick in enumerate(sorted(by_tick)):
        notes = by_tick[tick]
        delay = tick - prev_tick
        steps.append(
            Step(
                index=index,
                tick=tick,
                time_seconds=tick * TICK_SECONDS,
                delay_from_prev_rticks=delay,
                repeaters=Repeaters(chain=decompose_delay(delay), count=len(decompose_delay(delay))),
                notes=notes,
            )
        )
        if len(notes) >= BIG_CHORD_THRESHOLD:
            big_chord_steps.append(index)
        if any(n.octave_shift != 0 for n in notes):
            octave_shift_steps.append(index)
        prev_tick = tick

    warnings: list[Warning] = []
    if shifted_notes:
        lo, hi = min(shift_amounts), max(shift_amounts)
        range_text = f"{lo:+d}" if lo == hi else f"{lo:+d}〜{hi:+d}"
        warnings.append(
            Warning(
                type="octave_shift",
                message=f"{shifted_notes}音を音域に収めるため {range_text} オクターブシフトしました",
                steps=octave_shift_steps,
            )
        )
    for index in big_chord_steps:
        count = len(steps[index].notes)
        warnings.append(
            Warning(
                type="big_chord",
                message=f"ステップ{index}は同時{count}音です。分岐ダストを両側に伸ばす配線を推奨",
                steps=[index],
            )
        )

    total_rticks = steps[-1].tick if steps else 0
    meta = Meta(
        title=title,
        source_file=source_file,
        original_bpm=original_bpm,
        effective_bpm=effective_bpm,
        ticks_per_quarter=ticks_per_quarter,
        total_rticks=total_rticks,
        duration_seconds=total_rticks * TICK_SECONDS,
        step_count=len(steps),
        quantization=quantization_stats,
    )
    return meta, steps, warnings
