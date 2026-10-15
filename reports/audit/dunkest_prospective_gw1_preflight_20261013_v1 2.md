# Dunkest 2026/27 — prospective GW1 backtest preflight

- Status: **pre_match_frozen_awaiting_actuals**
- Frozen run: `20261013T072534Z_76c01a55`
- Forecast timestamp (UTC): `2026-10-13T07:25:34.776351+00:00`
- Workspace: `/Users/simone/Documents/Dunkest/data/workspaces/dunkest_preflight_20261013`
- Prediction rows: **552**
- Hashed pre-match snapshot files: **11**

## Acquisition and forecast integrity

- Dunkest market: 570 players and 30 coaches across 30 player teams and 30 coach teams.
- Availability archive: 11 timestamped observations; by turn {'1': 4, '2': 4, '3': 3}.
- Fixture list: 16 rows; turns {'1': 3, '2': 11, '3': 2}.
- Every required input snapshot has valid acquisition metadata before the earliest mapped fixture date: **True**.
- Post-game evaluation status: **not_ready** — expected because games have not been played and no result archive exists.
- Safe earliest result collection time (UTC): **2026-10-23T12:00:00+00:00** (`date_only_schedule_plus_36h`). The NBA schedule mapping contains dates at 00:00 UTC rather than exact tipoff times, so the collector uses a conservative 36-hour buffer after the latest date.

## Frozen candidate lineups

| Rank | Unique players | Coach | Expected team PDK | Players PDK | Coach PDK | Transfer malus | Budget |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 10 | Micah Nori | 200.18 | 183.41 | 16.77 | 0.0 | 95.0 CR |
| 2 | 10 | Doug Christie | 194.34 | 186.59 | 7.74 | 0.0 | 95.0 CR |
| 3 | 10 | Jamahl Mosley | 189.75 | 182.89 | 6.86 | 0.0 | 95.0 CR |

## Known acquisition/model limitations

- Forecast was generated on 2026-10-13 before the 2026-10-20 to 2026-10-22 scheduled fixture dates; model inputs are archived with hashes and acquisition timestamps.
- The fixture mapping stores calendar dates as 00:00 UTC, not exact tipoff times. Post-game collection therefore waits 36 hours after the latest mapped date (2026-10-23 12:00 UTC) and still requires complete player and coach actual coverage.
- The Turn 1 browser pass read 16/16 fixture cards. The Turn 2 and Turn 3 passes each read 15/16 because the non-target fixture 21/10 PHI VS NYK failed to load. All target-turn fixture cards were read (Turn 1: 3/3, Turn 2: 11/11, Turn 3: 2/2); all 30 player teams and 30 coach teams were present in the frozen market.
- Only 11 availability observations were captured (4/4/3 by turns), all timestamped. This is not a complete league injury feed; the separate official injury snapshot was also frozen.
- The predictor ignored inconsistent starter tags for CLE and DEN (14 and 12 tags respectively); their projections fall back to history/prices rather than trusting those tags.
- No post-match results exist yet. Metrics are intentionally withheld; the evaluator returns not_ready.
- Production current_lineups_market.csv and production data/raw files were not overwritten. All prediction artifacts and refreshable caches live under the isolated workspace.

## Verification

- Full test suite: **257 passed, 6800 warnings**.
- Python compilation and `git diff --check`: passed.
- Post-game runner guard: correctly refuses to collect anything before the safe cutoff.
- Snapshot hashes and all required pre-match acquisition timestamps: passed.

## Post-game execution

After the safe cutoff, run from the repository root:

```bash
./scripts/run_prospective_gw1_backtest.sh
```

The runner refreshes official Dunkest player histories and NBA player/team logs inside the isolated workspace, builds a fixture-linked player/coach result archive, and evaluates the frozen run. If coverage is incomplete, it stops without accepting complete lineup metrics.

Companion JSON includes SHA-256 hashes for every pre-match snapshot file and the runner.
