"""music21 で楽譜ファイル(.mid / .musicxml / .mxl)をパースし NoteEvent とサマリを生成する。

- 和音(Chord)は個々のノートに展開する
- タイは stripTies で結合し onset のみ採用(duration は結合後の長さを保持)
- MIDI ch10(打楽器)のトラックは is_percussion フラグを付け、NoteEvent には展開しない
  (通常マッピングから除外。Phase 5 issue #44 で対応)
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
    tracks: list[TrackInfo]


class ParsedScore(BaseModel):
    events: list[NoteEvent]
    summary: ScoreSummary


def _staff_number_of(part: m21stream.Stream) -> int | None:
    match = _STAFF_ID_RE.search(str(part.id)) if part.id is not None else None
    return int(match.group(1)) if match else None


def _channel_of(part: m21stream.Stream) -> int | None:
    inst = part.getInstrument(returnDefault=False)
    if inst is not None and inst.midiChannel is not None:
        return inst.midiChannel + 1  # music21 は 0 始まり(9 = 打楽器 ch10)
    return None


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
        for pitch in getattr(n, "pitches", ()):  # Chord は展開、Unpitched は空でスキップ
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


def parse_score(path: str | Path) -> ParsedScore:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"未対応の拡張子です: {ext}")

    score = converter.parse(path).stripTies()  # タイは score 全体で結合して onset のみ採用
    parts = list(score.parts)
    if not parts:
        parts = [score]

    # テンポマップ適用後の実秒(seconds モード用)。flatten は同一要素を参照するので id で引く
    seconds_by_id = {
        id(entry["element"]): float(entry["offsetSeconds"])
        for entry in score.flatten().secondsMap
    }

    events: list[NoteEvent] = []
    tracks: list[TrackInfo] = []
    for index, part in enumerate(parts):
        part_id = str(part.id) if part.id is not None else f"P{index}"
        staff_number = _staff_number_of(part)
        channel = _channel_of(part)
        is_percussion = channel == 10
        part_events = (
            []
            if is_percussion
            else list(
                _iter_note_events(part, part_id, staff_number, index, channel, seconds_by_id)
            )
        )
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
        duration_ql=float(score.highestTime),
        tracks=tracks,
    )
    return ParsedScore(events=events, summary=summary)
