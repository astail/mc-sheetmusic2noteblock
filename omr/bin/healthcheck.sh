#!/bin/sh
set -eu

test -f /tmp/omr-ready
kill -0 1
