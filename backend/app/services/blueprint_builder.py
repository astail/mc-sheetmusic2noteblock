"""量子化済みノート群から設計書のステップ列と meta を組み立てる(DESIGN.md §6・§7)。

- tick 昇順のユニーク集合 → Step 列。delay = tick_n − tick_{n−1}(先頭は曲頭 tick 0 からの遅延)
- リピーター分解: d → [4]×(d//4) + ([d%4] if d%4 else [])
- materials は services/materials.py(issue #16)、layout は issue #35 の責務
"""

from collections import defaultdict

from app import config
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
from app.services.pitch_mapper import map_percussion, map_pitch
from app.services.quantizer import QuantizedEvent

TICK_SECONDS = 0.1
# 同時発音がこの数以上の Step は big_chord 警告
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
    original_bpm: float | None,
    ticks_per_quarter: int | None,
    effective_bpm: float | None,
    quantization_stats: QuantizationStats,
    preset: str = "bass_harp_bell",
    transpose_semitones: int = 0,
) -> tuple[Meta, list[Step], list[Warning]]:
    """Step 列・meta・警告(big_chord / octave_shift / repeater_limit)を組み立てる。

    hands は quantized と同順で渡すこと。quantizer は入力イベントを並べ替え・デデュープ
    するため、パース順の events から作った hands は使えない。量子化後に
    `split_hands([q.event for q in quantized], ...)` で作るのが正しい。
    hand が "other" のイベントは設計書から除外する。
    ticks_per_quarter / effective_bpm は seconds モードでは None。
    """
    by_tick: dict[int, list[NotePlacement]] = defaultdict(list)
    shifted_notes = 0
    shift_amounts: list[int] = []
    # オクターブシフト/折込で異なる元ピッチが同じ出力音になる衝突をデデュープする
    seen_placements: set[tuple[int, str, int]] = set()
    merged_after_mapping = 0
    merged_ticks: set[int] = set()
    for q, hand in zip(quantized, hands):
        if hand == "other":
            continue
        if hand == "percussion":
            mapped = map_percussion(q.event.midi_pitch)
        else:
            mapped = map_pitch(
                q.event.midi_pitch, preset=preset, transpose_semitones=transpose_semitones
            )
        placement_key = (q.tick, mapped.instrument, mapped.clicks)
        if placement_key in seen_placements:
            merged_after_mapping += 1
            merged_ticks.add(q.tick)
            continue
        seen_placements.add(placement_key)
        inst = INSTRUMENTS[mapped.instrument]
        effective_midi = None if inst.is_percussion else inst.base_midi + mapped.clicks
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
                note_name=None if effective_midi is None else note_name(effective_midi),
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
                message=(
                    f"ステップ{index}は同時{count}音です。主バスから分岐ダストを"
                    "南北（±Z）の両側に伸ばし、音符ブロックを振り分けて配線してください"
                ),
                steps=[index],
            )
        )
    total_repeaters = sum(step.repeaters.count for step in steps)
    if total_repeaters > config.REPEATER_WARNING_THRESHOLD:
        warnings.append(
            Warning(
                type="repeater_limit",
                message=(
                    f"リピーター総数は{total_repeaters}個で、設定閾値の"
                    f"{config.REPEATER_WARNING_THRESHOLD}個を超えています。"
                    "曲を分割して複数の演奏装置に分けることを推奨します"
                ),
            )
        )
    if merged_after_mapping:
        tick_to_index = {s.tick: s.index for s in steps}
        warnings.append(
            Warning(
                type="merge",
                message=(
                    f"同一ステップで同じ音色・クリック数になる "
                    f"{merged_after_mapping} 音をマージしました"
                ),
                steps=sorted(tick_to_index[t] for t in merged_ticks),
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
