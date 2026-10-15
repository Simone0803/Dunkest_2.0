# Dunkest lineup backtest blocker resolution — 13 October 2026

## Status

**The collection/evaluation path is prepared; realized lineup scoring is waiting for the first gameweek to finish.** This is a timing dependency, not a prediction-model failure.

## Frozen run verified

- Run ID: `20261013T072534Z_76c01a55`
- Run directory: `data/workspaces/dunkest_preflight_20261013/predictions/20261013T072534Z_76c01a55`
- Season / gameweek: `2026-27` / GW1
- Fixture mapping: 16 verified NBA fixtures
- Pre-match snapshot hashes: 11/11 verified
- Required pre-match inputs: complete
- Source capture timestamps: valid and before kickoff
- Archived post-match results: not yet available

The evaluator was run against the exact frozen workspace path using a temporary output directory. It returned `not_ready` for the sole expected blocker: **no archived post-match result bundle exists yet**.

## What was fixed in code

- `scripts/build_dunkest_post_match_results_v1.py` now accepts `--run-dir`, so a frozen run can be evaluated from an isolated workspace without copying or modifying it.
- `scripts/evaluate_archived_run_post_match_v1.py` now accepts `--run-dir` and validates the run ID, season and gameweek against its manifest.
- Added regression tests for workspace runs and mismatched run IDs.
- The frozen prediction directory, production model/configuration, and historical raw data were not changed.

## When real results can be collected

The schedule stores some kickoff values as date-only midnight timestamps. The conservative shared timing rule therefore requires waiting until **`2026-10-23T12:00:00+00:00` (23 October 2026, 12:00 UTC; 14:00 in the Netherlands)** before collecting GW1 outcomes. Running early is blocked by design.

After that cutoff, run:

```bash
cd /Users/simone/Documents/Dunkest
bash scripts/run_prospective_gw1_backtest.sh
```

The script checks the cutoff, refreshes official Dunkest player-game histories and NBA boxscores inside the isolated workspace, links player results to the frozen NBA fixture IDs, computes coach points only when final scores and overtime evidence are available, archives immutable result files, and evaluates the same frozen lineups. Missing or ambiguous scores remain missing; they are never imputed as zero. If coverage is incomplete, inspect the workspace's `reports/backtest/post_match_collection_audit_20261013T072534Z_76c01a55_missing.csv` and audit JSON before rerunning.

## What cannot be reconstructed retrospectively

The historical complete-lineup backtest remains uncertifiable for rounds that lack authentic pre-tipoff snapshots. Historical weekly PDK/plusvalenza tables provide outcomes but do not prove which roster, credits, injury statuses, coach market and lineup choices were available before tipoff. Rebuilding these from post-game data would introduce look-ahead bias. The safe path is to use only historical rounds with authentic archived pre-match bundles and to accumulate complete prospective rounds going forward.

## Reproducibility

- Run the evaluator without results to validate the frozen inputs:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/evaluate_archived_run_post_match_v1.py \
  --data-dir data \
  --run-dir data/workspaces/dunkest_preflight_20261013/predictions/20261013T072534Z_76c01a55 \
  --output-dir /tmp/dunkest_post_match_preflight_check
```

- Run the post-match collection/evaluation pipeline after the safe cutoff with the shell command above.
