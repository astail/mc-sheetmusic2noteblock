#!/usr/bin/env python3
"""Controllable Audiveris stand-in used by wrapper unit tests."""

import json
import os
from pathlib import Path
import signal
import sys
import time
import zipfile


def ignore_term(_signum, _frame) -> None:
    if marker := os.environ.get("FAKE_AUDIVERIS_TERM_MARKER"):
        Path(marker).touch()


def write_mxl(path: Path) -> None:
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles>
</container>
"""
    score = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"><part-list/></score-partwise>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.recordare.musicxml")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("score.musicxml", score)


def main() -> int:
    args = sys.argv[1:]
    output_dir = Path(args[args.index("-output") + 1])
    input_path = Path(args[-1])
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = os.environ.get("FAKE_AUDIVERIS_TRACE")
    if trace_path:
        with Path(trace_path).open("a", encoding="utf-8") as trace:
            trace.write(json.dumps({"args": args, "input": str(input_path), "output": str(output_dir)}) + "\n")
    if started_path := os.environ.get("FAKE_AUDIVERIS_STARTED"):
        Path(started_path).write_text(str(os.getpid()), encoding="ascii")

    mode = os.environ.get("FAKE_AUDIVERIS_MODE", "success")
    if mode == "fail":
        print("private fake failure details", file=sys.stderr)
        return 9
    if mode == "hang":
        signal.signal(signal.SIGTERM, ignore_term)
        if pid_path := os.environ.get("FAKE_AUDIVERIS_PID"):
            Path(pid_path).write_text(str(os.getpid()), encoding="ascii")
        time.sleep(60)
    if mode == "blocking":
        release = Path(os.environ["FAKE_AUDIVERIS_RELEASE"])
        deadline = time.monotonic() + 10
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not release.exists():
            return 24
    if mode == "missing":
        return 0
    if mode == "invalid":
        (output_dir / "score.mxl").write_bytes(b"not a zip")
        return 0

    write_mxl(output_dir / "score.mxl")
    if mode == "multiple":
        write_mxl(output_dir / "other.mxl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
