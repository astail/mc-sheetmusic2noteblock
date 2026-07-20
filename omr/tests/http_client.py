#!/usr/bin/env python3
"""Post one image to a wrapper sharing this container's network namespace."""

from pathlib import Path
import secrets
import sys
from urllib.request import Request, urlopen


def main() -> None:
    input_path = Path(sys.argv[1])
    boundary = f"----omr-validation-{secrets.token_hex(12)}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="score.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + input_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = Request(
        "http://127.0.0.1:8080/transcribe",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(request, timeout=300) as response:
        response.read()


if __name__ == "__main__":
    main()
