"""music21 で楽譜ファイル(.mid / .musicxml / .mxl)をパースし NoteEvent とサマリを生成する。

- 和音(Chord)は個々のノートに展開する
- タイは stripTies で結合し onset のみ採用(duration は結合後の長さを保持)
- MIDI ch10(打楽器)のトラックは is_percussion フラグを付ける。Unpitched ノートは
  GM percussion map 上の実際の打楽器キー番号(storedInstrument.percMapPitch)を
  midi_pitch として NoteEvent 化する(pitch_mapper.map_percussion が3音色へ振り分ける)
"""

import re
from pathlib import Path

from music21 import converter
from music21 import stream as m21stream
from music21 import tempo as m21tempo
from pydantic import BaseModel

from app.models.events import NoteEvent

SUPPORTED_EXTENSIONS = {".mid", ".musicxml", ".mxl"}

# music21 は 2譜表パートを "P1-Staff1" / "P1-Staff2" のような id の PartStaff に分割する
_STAFF_ID_RE = re.compile(r"-Staff(\d+)$")


class TrackInfo(BaseModel):
    index: int
    part_id: str
    name: str | None = None
    staff_number: int | None = None
    is_percussion: bool = False
    note_count: int


class ScoreSummary(BaseModel):
    title: str | None = None
    original_bpm: float | None = None
    has_tempo_changes: bool = False
    midi_min: int | None = None
    midi_max: int | None = None
    note_count: int
    duration_ql: float
    measure_count: int = 0
    tracks: list[TrackInfo]


class ParsedScore(BaseModel):
    events: list[NoteEvent]
    summary: ScoreSummary


def staff_number_of(part: m21stream.Stream) -> int | None:
    match = _STAFF_ID_RE.search(str(part.id)) if part.id is not None else None
    return int(match.group(1)) if match else None


def _channel_of(part: m21stream.Stream) -> int | None:
    # 打楽器パートは Instrument が Part 直下でなくネストして挿入されるため recurse が必要
    inst = part.getInstrument(returnDefault=False, recurse=True)
    if inst is not None and inst.midiChannel is not None:
        return inst.midiChannel + 1  # music21 は 0 始まり(9 = 打楽器 ch10)
    return None


def _percussion_midi_pitch(n) -> int | None:
    stored = getattr(n, "storedInstrument", None)
    pitch = getattr(stored, "percMapPitch", None) if stored is not None else None
    return int(pitch) if pitch is not None else None


def _iter_note_events(
    part: m21stream.Stream,
    part_id: str,
    staff_number: int | None,
    track_index: int,
    channel: int | None,
    seconds_by_id: dict[int, float],
):
    for n in part.recurse().notes:
        offset = float(n.getOffsetInHierarchy(part))
        offset_seconds = seconds_by_id.get(id(n))
        try:
            beat = float(n.beat)
        except Exception:
            beat = None
        pitches = getattr(n, "pitches", ())
        if not pitches:
            # Unpitched(打楽器)は GM percussion map 上のキー番号を midi_pitch とする。
            # 対応するキーが無い場合(GM 標準外)は変換対象から静かに除外する
            if channel != 10:
                continue
            percussion_pitch = _percussion_midi_pitch(n)
            if percussion_pitch is None:
                continue
            yield NoteEvent(
                offset_ql=offset,
                offset_seconds=offset_seconds,
                duration_ql=float(n.duration.quarterLength),
                midi_pitch=percussion_pitch,
                part_id=part_id,
                staff_number=staff_number,
                track_index=track_index,
                channel=channel,
                measure=n.measureNumber,
                beat=beat,
                tie=n.tie.type if n.tie is not None else None,
            )
            continue
        for pitch in pitches:  # Chord は個々のノートに展開
            yield NoteEvent(
                offset_ql=offset,
                offset_seconds=offset_seconds,
                duration_ql=float(n.duration.quarterLength),
                midi_pitch=pitch.midi,
                part_id=part_id,
                staff_number=staff_number,
                track_index=track_index,
                channel=channel,
                measure=n.measureNumber,
                beat=beat,
                tie=n.tie.type if n.tie is not None else None,
            )


def _measure_starts(score: m21stream.Stream) -> list[float]:
    """複数 Part に重複する小節を時間位置でまとめ、1始まりの小節序数に使う。"""
    return sorted(
        {
            float(measure.getOffsetInHierarchy(score))
            for measure in score.recurse().getElementsByClass(m21stream.Measure)
        }
    )


def _seconds_at_offset(score: m21stream.Stream, offset_ql: float) -> float:
    """テンポマップを積分し、曲頭から指定 quarterLength までの実秒を返す。"""
    seconds = 0.0
    for start, end, mark in score.metronomeMarkBoundaries():
        start_ql = float(start)
        end_ql = float(end)
        if offset_ql <= start_ql:
            break
        duration_ql = min(offset_ql, end_ql) - start_ql
        if duration_ql > 0:
            quarter_bpm = mark.getQuarterBPM()
            if quarter_bpm is None:
                raise ValueError("小節開始位置のテンポを計算できません")
            seconds += duration_ql * 60.0 / float(quarter_bpm)
        if offset_ql <= end_ql:
            break
    return seconds


def parse_score(
    path: str | Path,
    measure_range: tuple[int, int] | None = None,
) -> ParsedScore:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"未対応の拡張子です: {ext}")

    score = converter.parse(path).stripTies()  # タイは score 全体で結合して onset のみ採用
    parts = list(score.parts)
    if not parts:
        parts = [score]

    measure_starts = _measure_starts(score)
    measure_count = len(measure_starts)
    range_start_ql = 0.0
    range_end_ql = float(score.highestTime)
    range_start_seconds = 0.0
    if measure_range is not None:
        start, end = measure_range
        if start < 1 or start > end:
            raise ValueError("measure_range は 1 以上かつ 開始 <= 終了 であること")
        if end > measure_count:
            raise ValueError(
                f"measure_range は楽譜の小節範囲 1〜{measure_count} 内で指定してください"
            )
        range_start_ql = measure_starts[start - 1]
        range_end_ql = (
            measure_starts[end] if end < measure_count else float(score.highestTime)
        )
        range_start_seconds = _seconds_at_offset(score, range_start_ql)

    # テンポマップ適用後の実秒(seconds モード用)。flatten は同一要素を参照するので id で引く
    seconds_by_id = {
        id(entry["element"]): float(entry["offsetSeconds"])
        for entry in score.flatten().secondsMap
    }

    events: list[NoteEvent] = []
    tracks: list[TrackInfo] = []
    for index, part in enumerate(parts):
        part_id = str(part.id) if part.id is not None else f"P{index}"
        staff_number = staff_number_of(part)
        channel = _channel_of(part)
        is_percussion = channel == 10
        part_events = list(
            _iter_note_events(part, part_id, staff_number, index, channel, seconds_by_id)
        )
        if measure_range is not None:
            part_events = [
                event.model_copy(
                    update={
                        "offset_ql": event.offset_ql - range_start_ql,
                        "offset_seconds": (
                            max(0.0, event.offset_seconds - range_start_seconds)
                            if event.offset_seconds is not None
                            else None
                        ),
                    }
                )
                for event in part_events
                if range_start_ql <= event.offset_ql < range_end_ql
            ]
        events.extend(part_events)
        tracks.append(
            TrackInfo(
                index=index,
                part_id=part_id,
                name=part.partName,
                staff_number=staff_number,
                is_percussion=is_percussion,
                note_count=len(part_events),
            )
        )

    if measure_range is not None and not events:
        start, end = measure_range
        raise ValueError(f"measure_range {start}〜{end} に変換対象の音符がありません")

    # 拍単位が4分音符以外の表記(2分音符=60 等)も4分音符換算の BPM に正規化する
    quarter_bpms = [
        float(qbpm)
        for mark in score.recurse().getElementsByClass(m21tempo.MetronomeMark)
        if (qbpm := mark.getQuarterBPM()) is not None
    ]

    pitches = [e.midi_pitch for e in events]
    summary = ScoreSummary(
        title=score.metadata.title if score.metadata is not None else None,
        original_bpm=quarter_bpms[0] if quarter_bpms else None,
        has_tempo_changes=len(set(quarter_bpms)) > 1,
        midi_min=min(pitches) if pitches else None,
        midi_max=max(pitches) if pitches else None,
        note_count=len(events),
        duration_ql=range_end_ql - range_start_ql,
        measure_count=measure_count,
        tracks=tracks,
    )
    return ParsedScore(events=events, summary=summary)
