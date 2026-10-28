#!/usr/bin/env bash
# Start the outreach dashboard (macOS / Linux).
#
#   dashboard/start.sh                 # uses ./outreach (created if missing)
#   dashboard/start.sh path/to/outreach
#
# First run creates dashboard/.venv and installs dependencies there.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "Python 3.10+ is required (found: $("$PY" --version 2>&1 || echo none))." >&2
  echo "Set PYTHON=/path/to/python3.10+ and run again." >&2
  exit 1
fi

VENV="$ROOT/dashboard/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtual environment in dashboard/.venv ..."
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r dashboard/requirements.txt

DATA="${1:-$ROOT/outreach}"
mkdir -p "$DATA"
echo "Data folder: $DATA"
exec "$VENV/bin/python" -m dashboard --data "$DATA" --open "${@:2}"
