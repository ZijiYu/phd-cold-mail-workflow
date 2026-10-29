#!/usr/bin/env bash
# Start the outreach dashboard in the foreground (macOS / Linux).
#
#   dashboard/start.sh                 # uses ./outreach (created if missing)
#   dashboard/start.sh path/to/outreach
#
# For a background start with one short command, use dashboard/phd
# (`dashboard/phd install` adds `phd` to your shell).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${1:-}" ]; then export PHD_DATA="$1"; shift; fi
exec "$HERE/phd" run ${@+"$@"}
