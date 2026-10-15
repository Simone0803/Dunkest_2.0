#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS="${DUNKEST_BACKTEST_DATA_DIR:-$ROOT/data/workspaces/dunkest_preflight_20261013}"
SOURCE_RUN_ID="${DUNKEST_BACKTEST_SOURCE_RUN_ID:-20261013T184846Z_21d331f5}"
VARIANT_ROOT="$WS/predictions/strategy_variants_${SOURCE_RUN_ID}"
REFERENCE_KEY="risk_adjusted_corrected_gain"
RUN_ID="${SOURCE_RUN_ID}__${REFERENCE_KEY}"
REFERENCE_VARIANT="$VARIANT_ROOT/$RUN_ID"
TOP_LEVEL_RUN="$WS/predictions/$RUN_ID"
OUT="$WS/reports/backtest/strategy_comparison"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f "$REFERENCE_VARIANT/manifest.json" ]]; then
  echo "Frozen strategy variants are missing. Run scripts/build_dunkest_gw1_strategy_variants_v3.py with DUNKEST_BACKTEST_SOURCE_RUN_ID set to the fresh frozen run ID." >&2
  exit 2
fi

# Recheck freshness at scoring time; a timestamp before tip-off alone is not enough.
"$ROOT/.venv/bin/python" - "$REFERENCE_VARIANT" <<'PY'
import json, sys
from pathlib import Path
import pandas as pd
run=Path(sys.argv[1])
m=json.loads((run/"manifest.json").read_text())
cfg=m["configuration"]
run_ts=pd.to_datetime(m.get("timestamp"),utc=True,errors="coerce")
maps=[e for e in m["pre_match_snapshot"]["files"] if e["path"].startswith("dunkest_fixture_mapping_")]
if not maps: raise SystemExit("No frozen fixture mapping.")
mapping=pd.read_parquet(run/"pre_match_snapshot"/maps[0]["path"])
mapping=mapping.loc[pd.to_numeric(mapping["dunkest_gameweek"],errors="coerce").eq(int(cfg["target_gameweek"]))]
kick=pd.to_datetime(mapping["game_datetime_utc"],utc=True,errors="coerce")
if mapping.empty or kick.isna().any() or pd.isna(run_ts): raise SystemExit("Invalid run timestamp or fixture mapping.")
earliest=kick.min()
if run_ts>=earliest or (earliest-run_ts).total_seconds()>36*3600: raise SystemExit("Refusing scoring: forecast run is not within 36 hours before the earliest kickoff.")
entries={e["path"]:e for e in m["pre_match_snapshot"]["files"]}
required=["current_lineups_market.csv","lineups_availability.csv",f"player_credits_{cfg['season_id']}_gw{cfg['target_gameweek']}.parquet",f"coach_market_{cfg['season_id']}_gw{cfg['target_gameweek']}.parquet",f"injuries_{cfg['season_id']}_gw{cfg['target_gameweek']}.parquet"]
for name in required:
    if name not in entries or name+".meta.json" not in entries: raise SystemExit(f"Missing snapshot/metadata: {name}")
    meta=json.loads((run/"pre_match_snapshot"/(name+".meta.json")).read_text())
    ts=pd.to_datetime(meta.get("fetched_at") or meta.get("captured_at_utc") or meta.get("retrieved_at_utc"),utc=True,errors="coerce")
    age=(earliest-ts).total_seconds()/3600 if pd.notna(ts) else float("inf")
    if pd.isna(ts) or ts>=earliest or age>36: raise SystemExit(f"Refusing scoring: stale or invalid snapshot {name}, age={age:.1f}h.")
print("Freshness gate passed: run and all required pregame snapshots are within 36h of earliest kickoff.")
PY
mkdir -p "$WS/predictions"
if [[ ! -f "$TOP_LEVEL_RUN/manifest.json" ]]; then
  cp -R "$REFERENCE_VARIANT" "$TOP_LEVEL_RUN"
fi

# This performs the safe-cutoff check, collects official results once into the
# isolated workspace, archives fixture-linked actuals, and evaluates the
# reference risk-adjusted strategy. It must not be run before the safe cutoff.
DUNKEST_BACKTEST_DATA_DIR="$WS" DUNKEST_BACKTEST_RUN_ID="$RUN_ID" \
  bash "$ROOT/scripts/run_prospective_gw1_backtest.sh"

mkdir -p "$OUT"
for key in risk_adjusted_corrected_gain expected_value_corrected_gain risk_adjusted_uncorrected_gain expected_value_uncorrected_gain risk_adjusted_no_gain expected_value_no_gain; do
  run_id="${SOURCE_RUN_ID}__${key}"
  run_dir="$VARIANT_ROOT/$run_id"
  report_dir="$OUT/$key"
  echo "Evaluating frozen strategy: $key"
  "$ROOT/.venv/bin/python" "$ROOT/scripts/evaluate_archived_run_post_match_v1.py" \
    --data-dir "$WS" --season-id 26 --gameweek 1 --run-dir "$run_dir" \
    --output-dir "$report_dir"
done

"$ROOT/.venv/bin/python" - "$OUT" "$ROOT/reports/audit/dunkest_gw1_strategy_comparison_${SOURCE_RUN_ID}_v1" <<'PY'
import json, sys
from pathlib import Path
import pandas as pd
out=Path(sys.argv[1]); stem=Path(sys.argv[2])
keys=["risk_adjusted_corrected_gain","expected_value_corrected_gain","risk_adjusted_uncorrected_gain","expected_value_uncorrected_gain","risk_adjusted_no_gain","expected_value_no_gain"]
rows=[]
for key in keys:
    reports=list((out/key).glob("post_match_evaluation_*.json"))
    if len(reports)!=1: raise SystemExit(f"Expected one evaluator report for {key}, found {len(reports)}")
    report=json.loads(reports[0].read_text())
    if report.get("status")!="ready":
        raise SystemExit(f"{key} is not fully scored (status={report.get('status')}); do not compare incomplete lineups.")
    lm=report.get("metrics",{})
    rows.append({"variant":key,"status":report["status"],
      "complete_lineups":lm.get("complete_lineup_ranks"),
      "rank1_realized_team_score":lm.get("rank1_realized_team_score"),
      "best_of_3_realized_team_score":lm.get("best_of_k_realized_team_score"),
      "player_mae":lm.get("player_mae"),"player_rmse":lm.get("player_rmse"),
      "player_actual_coverage":lm.get("player_actual_coverage")})
df=pd.DataFrame(rows)
base=df.loc[df.variant.eq("risk_adjusted_corrected_gain")].iloc[0]
df["delta_rank1_vs_risk_adjusted_gain"]=df["rank1_realized_team_score"]-base["rank1_realized_team_score"]
df["delta_best_of_3_vs_risk_adjusted_gain"]=df["best_of_3_realized_team_score"]-base["best_of_3_realized_team_score"]
df.to_csv(stem.with_suffix(".csv"),index=False)
payload={"variants":rows,"reference":"risk_adjusted_corrected_gain",
 "interpretation":"Single prospective gameweek; descriptive paired comparison only, not statistical proof or tuning evidence.",
 "metrics_policy":"All six strategies must have complete lineups and linked player/coach actuals; missing scores are never imputed as zero."}
stem.with_suffix(".json").write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
lines=["# Prospective GW1 strategy comparison","",
 "All six lineup sets share the same frozen pregame forecasts and market snapshots.",
 "The reference is risk-adjusted plus corrected plusvalenza. Other variants change the optimizer objective, use a reconstructed uncorrected plusvalenza estimate, or exclude plusvalenza from optimization.",
 "","## Realized scores","",df.to_string(index=False),"",
 "This is one prospective gameweek, so differences are descriptive and do not establish statistical significance. Keep the risk-adjusted objective only if repeated walk-forward/holdout results support it.",
 "","Missing player or coach outcomes are not scored as zero.",""]
stem.with_suffix(".md").write_text("\n".join(lines),encoding="utf-8")
print(df.to_string(index=False))
print("Wrote",stem.with_suffix(".md"),stem.with_suffix(".json"),stem.with_suffix(".csv"))
PY
