#!/bin/bash
set -u
ROOT="/Users/simone/Documents/Dunkest"
STATUS="$ROOT/reports/audit/dunkest_gw1_prelock_capture_20261018.exit"
LOG="$ROOT/reports/audit/dunkest_pdk_refinement_20261018_v1_run.log"
EXIT="$ROOT/reports/audit/dunkest_pdk_refinement_20261018_v1.exit"
cd "$ROOT" || exit 10
mkdir -p reports/audit
printf 'Queued at %s UTC; waiting for pre-lock capture to finish.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
while [ ! -f "$STATUS" ]; do sleep 15; done
printf 'Capture ended with exit=%s at %s UTC.\n' "$(cat "$STATUS")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
# Let the independent archive-review watcher finish before using CPU for model search.
while kill -0 98473 2>/dev/null; do sleep 10; done
printf 'Focused refinement started at %s UTC.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
.venv/bin/python scripts/grid_search_dunkest_pdk_refinement_20261018_v1.py >> "$LOG" 2>&1
RC=$?
printf '%s\n' "$RC" > "$EXIT"
printf 'Focused refinement finished at %s UTC; exit=%s.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RC" >> "$LOG"
exit "$RC"
