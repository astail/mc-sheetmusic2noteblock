#!/bin/sh
set -eu

# Fail startup before reporting healthy if the installed CLI or native
# dependencies cannot be loaded.
Audiveris -version
touch /tmp/omr-ready

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "OMR container is ready; the HTTP wrapper will be provided in issue #41."

wait_pid=""

shutdown() {
    if [ -n "${wait_pid}" ]; then
        kill "${wait_pid}" 2>/dev/null || true
        wait "${wait_pid}" 2>/dev/null || true
    fi
    exit 0
}

trap shutdown TERM INT

while :; do
    sleep 3600 &
    wait_pid=$!
    wait "${wait_pid}" || true
done
