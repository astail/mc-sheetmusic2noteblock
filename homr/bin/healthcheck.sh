#!/bin/sh
set -eu

python3 - <<'PY'
import os
from urllib.request import urlopen

port = os.environ.get("OMR_PORT") or "8080"
with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as response:
    assert response.status == 200
    assert response.read() == b'{"status":"ok"}'
PY
