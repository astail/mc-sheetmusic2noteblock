#!/usr/bin/env python3
"""Controllable Audiveris stand-in used by wrapper unit tests."""

import json
import os
from pathlib import Path
import signal
import sys
import time
import zipfile


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

    mode = os.environ.get("FAKE_AUDIVERIS_MODE", "success")
    if mode == "fail":
        print("private fake failure details", file=sys.stderr)
        return 9
    if mode == "hang":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if pid_path := os.environ.get("FAKE_AUDIVERIS_PID"):
            Path(pid_path).write_text(str(os.getpid()), encoding="ascii")
        time.sleep(60)
    if mode == "guard":
        guard = Path(os.environ["FAKE_AUDIVERIS_GUARD"])
        try:
            descriptor = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return 23
        os.close(descriptor)
        try:
            time.sleep(0.15)
        finally:
            guard.unlink(missing_ok=True)
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
