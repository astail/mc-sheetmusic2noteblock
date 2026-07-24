#!/usr/bin/env python3
"""Controllable homr stand-in used by wrapper unit tests."""

import json
import os
from pathlib import Path
import signal
import sys
import time

_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"><part-list/></score-partwise>
"""


def ignore_term(_signum, _frame) -> None:
    if marker := os.environ.get("FAKE_HOMR_TERM_MARKER"):
        Path(marker).touch()


def main() -> int:
    image_path = Path(sys.argv[-1])
    trace_path = os.environ.get("FAKE_HOMR_TRACE")
    if trace_path:
        with Path(trace_path).open("a", encoding="utf-8") as trace:
            trace.write(json.dumps({"args": sys.argv[1:], "image": str(image_path)}) + "\n")
    if started_path := os.environ.get("FAKE_HOMR_STARTED"):
        Path(started_path).write_text(str(os.getpid()), encoding="ascii")

    mode = os.environ.get("FAKE_HOMR_MODE", "success")
    if mode == "fail":
        print("private fake failure details", file=sys.stderr)
        return 1
    if mode == "hang":
        signal.signal(signal.SIGTERM, ignore_term)
        if pid_path := os.environ.get("FAKE_HOMR_PID"):
            Path(pid_path).write_text(str(os.getpid()), encoding="ascii")
        time.sleep(60)
    if mode == "blocking":
        release = Path(os.environ["FAKE_HOMR_RELEASE"])
        deadline = time.monotonic() + 10
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not release.exists():
            return 24
    if mode == "missing":
        return 0
    if mode == "empty":
        image_path.with_suffix(".musicxml").write_bytes(b"")
        return 0

    image_path.with_suffix(".musicxml").write_text(_MUSICXML, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
