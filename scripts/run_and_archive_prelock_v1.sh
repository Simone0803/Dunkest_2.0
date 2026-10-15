#!/usr/bin/env bash
set -euo pipefail

# Run the production season opener only inside the certified pre-lock window,
# then archive the exact run with the strict immutable snapshot gate.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="$ROOT/.venv/bin/python"
MAX_HOURS="${DUNKEST_MAX_PRELOCK_HOURS:-36}"
SEASON_ID="${DUNKEST_SEASON_ID:-26}"
GAMEWEEK="${DUNKEST_GAMEWEEK:-1}"

# Refuse early/late execution before launching the expensive browser/model flow.
# Use the latest already-frozen fixture map only for this preflight; the strict
# archive script revalidates the fresh run's own fixture mapping afterwards.
"$PYTHON" - "$ROOT" "$SEASON_ID" "$GAMEWEEK" "$MAX_HOURS" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
root=Path(sys.argv[1]); season_id=sys.argv[2]; gw=int(sys.argv[3]); max_hours=float(sys.argv[4])
runs=[]
for manifest_path in (root/'data/predictions').glob('*/manifest.json'):
    try: manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception: continue
    cfg=manifest.get('configuration', {})
    if str(cfg.get('season_id','')) != season_id or int(cfg.get('target_gameweek',-1) or -1) != gw:
        continue
    snap=manifest_path.parent/'pre_match_snapshot'
    maps=sorted(snap.glob(f'dunkest_fixture_mapping_{season_id}_*.parquet'))
    if not maps: continue
    try:
        mapping=pd.read_parquet(maps[0])
        mapping=mapping.loc[pd.to_numeric(mapping.get('dunkest_gameweek'),errors='coerce').eq(gw)]
        kick=pd.to_datetime(mapping.get('game_datetime_utc'),utc=True,errors='coerce').dropna()
        ts=pd.to_datetime(manifest.get('timestamp'),utc=True,errors='coerce')
        if kick.empty or pd.isna(ts): continue
        runs.append((ts,manifest_path.parent.name,kick.min()))
    except Exception: continue
if not runs:
    raise SystemExit('Preflight blocked: no prior fixture-linked run exists to establish the upcoming kickoff. Run the normal pipeline once to discover the slate, then retry inside the pre-lock window.')
_, prior_run, kickoff=max(runs,key=lambda x:x[0])
now=pd.Timestamp(datetime.now(timezone.utc))
hours=(kickoff-now).total_seconds()/3600
print(f'Preflight: season_id={season_id}, gameweek={gw}, earliest_kickoff_utc={kickoff.isoformat()}, hours_until_kickoff={hours:.2f}, prior_run={prior_run}')
if hours < 0:
    raise SystemExit('Preflight blocked: earliest kickoff has passed; refusing to create a pre-lock archive.')
if hours > max_hours:
    raise SystemExit(f'Preflight blocked: too early ({hours:.2f}h until kickoff; maximum is {max_hours:.2f}h). Retry inside the pre-lock window. No model run or archive was created.')
PY

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Pre-lock window open. Running season opener for season_id=$SEASON_ID gameweek=$GAMEWEEK."
bash "$ROOT/run-season-opener.sh" --turno 1

RUN_ID="$("$PYTHON" - "$ROOT" "$SEASON_ID" "$GAMEWEEK" "$START_UTC" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
root=Path(sys.argv[1]); season_id=sys.argv[2]; gw=int(sys.argv[3])
start=datetime.fromisoformat(sys.argv[4].replace('Z','+00:00'))
candidates=[]
for path in (root/'data/predictions').glob('*/manifest.json'):
    try: manifest=json.loads(path.read_text(encoding='utf-8'))
    except Exception: continue
    cfg=manifest.get('configuration', {})
    if str(cfg.get('season_id','')) != season_id or int(cfg.get('target_gameweek',-1) or -1) != gw:
        continue
    try: ts=datetime.fromisoformat(str(manifest['timestamp']).replace('Z','+00:00'))
    except Exception: continue
    if ts.tzinfo is None: ts=ts.replace(tzinfo=timezone.utc)
    if ts.astimezone(timezone.utc) >= start.astimezone(timezone.utc):
        candidates.append((ts,path.parent.name))
if not candidates:
    raise SystemExit('No new prediction run was produced after this script started.')
print(max(candidates)[1])
PY
)"

echo "Archiving run $RUN_ID with immutable hashes and explicit pre-lock eligibility status."
# Use the canonical archive implementation consumed by the independent reviewer
# and post-match evaluator. The legacy no-underscore script used an incompatible
# run_payload layout and omitted the immutable registry expected downstream.
"$PYTHON" "$ROOT/scripts/archive_dunkest_pre_lock_run_v1.py" --run-id "$RUN_ID" --max-age-hours "$MAX_HOURS"
echo "Pre-lock archive created at data/archives/pre_lock/season_id=$SEASON_ID/gw=$GAMEWEEK/$RUN_ID; inspect pre_lock_eligible before treating it as certified evidence."
