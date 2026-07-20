#!/bin/sh
set -eu

# Fail startup before reporting healthy if the installed CLI or native
# dependencies cannot be loaded.
Audiveris -version

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec python3 -m uvicorn wrapper.server:app \
    --host 0.0.0.0 \
    --port "${OMR_PORT:-8080}" \
    --timeout-graceful-shutdown "${OMR_GRACEFUL_SHUTDOWN_SECONDS:-3}"
