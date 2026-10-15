#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${DUNKEST_BACKTEST_DATA_DIR:-$ROOT/data/workspaces/dunkest_preflight_20261013}"
RUN_ID="${DUNKEST_BACKTEST_RUN_ID:-20261013T072534Z_76c01a55}"
RUN_DIR="$WS/predictions/$RUN_ID"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f "$RUN_DIR/manifest.json" ]]; then
  echo "Frozen prediction run not found: $RUN_DIR" >&2
  exit 2
fi

# The NBA schedule source currently encodes some fixtures as date-only
# timestamps at 00:00 UTC. The shared helper therefore requires 36 hours after
# the latest mapped date before any post-game results are collected.
"$ROOT/.venv/bin/python" - "$RUN_DIR" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from dunkest.backtest.timing import safe_postgame_retrieval_cutoff
run_dir = Path(sys.argv[1])
manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
mapping_entry = next((item for item in manifest.get("pre_match_snapshot", {}).get("files", []) if str(item.get("path", "")).startswith("dunkest_fixture_mapping_")), None)
if mapping_entry is None:
    raise SystemExit("Frozen run has no fixture mapping snapshot.")
mapping = pd.read_parquet(run_dir / "pre_match_snapshot" / mapping_entry["path"])
cutoff, mode = safe_postgame_retrieval_cutoff(mapping.loc[mapping['dunkest_gameweek'].astype(int).eq(1), 'game_datetime_utc'])
now = pd.Timestamp(datetime.now(timezone.utc))
print(f"Post-game timing mode: {mode}")
print(f"Minimum safe collection time (UTC): {cutoff.isoformat()}")
if now < cutoff:
    print(f"Too early; wait until {cutoff.isoformat()}. No result collection was started.", file=sys.stderr)
    raise SystemExit(3)
PY

# Fetch official per-player Dunkest game histories into this isolated workspace.
# The checkpoint is also kept under the workspace, not the production raw folder.
"$ROOT/.venv/bin/python" "$ROOT/scripts/collect_dunkest_player_games_current_season_v1.py" \
  --data-dir "$WS" \
  --market "$RUN_DIR/pre_match_snapshot/player_credits_26_gw1.parquet" \
  --catalog "$ROOT/data/raw/dunkest_player_games_history_v1/player_catalog_current.json" \
  --output-dir "$WS/raw_postgame/player_games"

# Refresh NBA player/team boxscores and other current-season data in the isolated
# workspace. Cache writes use workspace-local atomic replacements.
"$ROOT/.venv/bin/python" - "$WS/season_opener_preflight.yaml" <<'PY'
import sys
from pathlib import Path
from dunkest.config import Settings
from dunkest.pipeline.collect import run_collect
settings = Settings.from_yaml(Path(sys.argv[1]))
print(run_collect(settings, force_refresh=True))
PY

mkdir -p "$WS/reports/backtest"
if ! "$ROOT/.venv/bin/python" "$ROOT/scripts/build_dunkest_post_match_results_v1.py" \
  --data-dir "$WS" \
  --run-id "$RUN_ID" \
  --player-games "$WS/processed/official_dunkest_player_games_2026-27.parquet" \
  --team-logs "$WS/processed/team_game_logs_2026-27.parquet" \
  --player-logs "$WS/processed/player_game_logs_2026-27.parquet" \
  --output-dir "$WS/reports/backtest"; then
  echo "Actuals are incomplete or not fixture-linked. No complete archive/metrics were accepted; inspect the collection audit in $WS/reports/backtest." >&2
  exit 2
fi

"$ROOT/.venv/bin/python" "$ROOT/scripts/evaluate_archived_run_post_match_v1.py" \
  --data-dir "$WS" \
  --season-id 26 --gameweek 1 --run-id "$RUN_ID" \
  --output-dir "$WS/reports/backtest"
