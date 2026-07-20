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
exec sleep infinity
