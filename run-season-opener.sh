#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$SCRIPT_DIR/.venv/bin/python" -m dunkest season-opener --config "$SCRIPT_DIR/config/season_opener.yaml" "$@"
