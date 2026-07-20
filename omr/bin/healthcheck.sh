#!/bin/sh
set -eu

python3 - <<'PY'
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8080/healthz", timeout=2) as response:
    assert response.status == 200
    assert response.read() == b'{"status":"ok"}'
PY
