"""hand_split の完了条件: twinkle_both_hands.musicxml(譜表判別)と twinkle.mid(フォールバック)。"""

from pathlib import Path

from app.models.events import NoteEvent
from app.services.hand_split import split_hands
from app.services.parser import parse_score

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _event(midi: int, track: int = 0, staff: int | None = None) -> NoteEvent:
    return NoteEvent(
        offset_ql=0.0,
        duration_ql=1.0,
        midi_pitch=midi,
        part_id=f"P{track}",
        staff_number=staff,
        track_index=track,
    )


def test_twinkle_both_hands_staff_rule():
    parsed = parse_score(FIXTURES / "twinkle_both_hands.musicxml")
    hands = split_hands(parsed.events)
    rights = [e for e, h in zip(parsed.events, hands) if h == "right"]
    lefts = [e for e, h in zip(parsed.events, hands) if h == "left"]
    assert len(rights) == 14  # staff 1 = メロディ
    assert len(lefts) == 12  # staff 2 = 和音
    assert all(e.staff_number == 1 for e in rights)
    assert all(e.staff_number == 2 for e in lefts)


def test_twinkle_midi_two_track_order_fallback():
    parsed = parse_score(FIXTURES / "twinkle.mid")
    hands = split_hands(parsed.events)
    rights = [e for e, h in zip(parsed.events, hands) if h == "right"]
    lefts = [e for e, h in zip(parsed.events, hands) if h == "left"]
    assert len(rights) == 14  # 先のトラック = 右手
    assert len(lefts) == 12  # 後のトラック = 左手


def test_track_name_heuristic():
    events = [_event(60, track=0), _event(48, track=1)]
    hands = split_hands(events, track_names={0: "L.H.", 1: "Right Hand"})
    assert hands == ["left", "right"]


def test_track_name_japanese():
    events = [_event(60, track=0), _event(48, track=1)]
    hands = split_hands(events, track_names={0: "左手", 1: "右手"})
    assert hands == ["left", "right"]


def test_single_track_pitch_split_at_c4():
    parsed = parse_score(FIXTURES / "scale_c_major.musicxml")
    hands = split_hands(parsed.events)
    assert set(hands) == {"right"}  # C4〜C5 はすべて右手

    events = [_event(59), _event(60), _event(72), _event(36)]
    assert split_hands(events) == ["left", "right", "right", "left"]


def test_hand_assignment_override():
    parsed = parse_score(FIXTURES / "twinkle.mid")
    tracks = sorted({e.track_index for e in parsed.events})
    hands = split_hands(
        parsed.events,
        hand_assignment={f"track_{tracks[0]}": "left", f"track_{tracks[1]}": "ignore"},
    )
    by_track = {t: set() for t in tracks}
    for e, h in zip(parsed.events, hands):
        by_track[e.track_index].add(h)
    assert by_track[tracks[0]] == {"left"}
    assert by_track[tracks[1]] == {"other"}  # ignore は other


def test_override_beats_staff():
    events = [_event(60, staff=1), _event(48, staff=2)]
    hands = split_hands(events, hand_assignment={"track_0": "left"})
    assert hands == ["left", "left"]
