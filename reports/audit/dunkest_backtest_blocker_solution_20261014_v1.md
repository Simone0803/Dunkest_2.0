# Historical lineup backtest blocker — implemented fallback and prospective recovery

Generated UTC: 2026-10-14

## Decision

The missing historical pre-lock market cannot be recovered reliably from the files currently available. The public Dunkest API probes did not find an unauthenticated endpoint to enumerate historical schedules, and historical outcomes do not establish what roster, CR, availability, or coach market was visible before lock. Reconstructing these states after games would create look-ahead risk.

The selected solution is therefore a two-track evaluation policy:

1. **Use official historical Dunkest player PDK for leakage-controlled player-model validation now.** This is measurable from verified game-level outcomes and strictly past-only features.
2. **Do not certify historical lineup strategy rankings from reconstructed prices/availability.** Keep the existing lineup proxy as exploratory sensitivity only, and collect immutable prospective pre-lock evidence for the 2026/27 season so exact lineup policies can be compared after results arrive.

This separates a solvable question (does the player forecast predict official PDK?) from a currently unidentifiable one (which complete historical Dunkest roster would have won given the actual pre-lock market and transfer state?).

## Evidence and results

### Player forecast: usable validation evidence

The existing official-target walk-forward dataset contains 93,766 labeled player-games from 2020/21–2024/25. Test folds are chronological: 2022/23, 2023/24, 2024/25, with earlier seasons used for training.

| Test season | Random-forest MAE | Previous-10 baseline MAE | RF bias (predicted − actual) |
|---|---:|---:|---:|
| 2022/23 | 7.578 | 7.769 | -0.170 |
| 2023/24 | 7.597 | 7.765 | +0.022 |
| 2024/25 | 7.589 | 7.792 | -0.114 |
| Pooled, weighted by test rows | 7.588 | 7.775 | about -0.09 |

This is evidence of a modest and consistent improvement in **player score prediction**, not evidence that an optimizer policy wins. 2025/26 has already been inspected by multiple experiments and is not an untouched final holdout. The 2026/27 GW1 prospective test remains frozen until 2026-10-23 12:00 UTC.

### Lineup optimizer: current proxy is not decision-grade

The latest reconstructed game-level experiment (V8) has:

- Strict observed-only paired lineup rounds: **8**. Pooled mean model-minus-baseline: **−8.70 PDK**, with substantial season heterogeneity.
- Expanded official-record sensitivity: **13** paired rounds. Mean difference: **+6.54 PDK**, paired bootstrap 95% interval **[−4.46, +18.45]**.
- Explicit zero-for-missing proxy: **458** rounds and a large apparent gain, but this depends on treating absent historical player-round outcomes as zero and on a reconstructed candidate universe. It is exploratory and must not drive production strategy selection.

The conflicting strict and proxy estimates show why the apparent positive proxy result cannot be promoted. Historical coach CR, complete pre-lock roster/availability, and transfer carry-over are missing. No lineup strategy is currently certified superior.

### Current prospective run: correctly rejected for pre-lock certification

Run `20261014T175113Z_7c1f0803` has a verified 16-fixture map, but the earliest kickoff in its archived mapping is `2026-10-20T00:00:00Z`. The run and required snapshots were **126.1–126.2 hours** before that time, exceeding the 36-hour certification window. The strict archiver returned `not_certified` and created no certified archive. This is the correct result.

## Implemented alternative

Added `scripts/run_and_archive_prelock_v1.sh`.

The script:
1. Checks the latest fixture-linked run to identify the earliest kickoff for the configured season/gameweek.
2. Refuses to launch an expensive scrape/model run outside the configured pre-lock window (default 36 hours), or after kickoff.
3. When the window opens, runs `bash run-season-opener.sh --turno 1`.
4. Identifies the newly created run from its manifest timestamp.
5. Invokes `scripts/archive_dunkest_prelock_run_v1.py`, which independently validates the new run's own fixture mapping, source hashes, capture timestamps, and freshness before creating a hash-verified immutable archive.
6. Fails closed if any evidence is missing, stale, post-lock, or inconsistent.

Run it from the repository root with:

```bash
bash scripts/run_and_archive_prelock_v1.sh
```

Defaults are season ID 26, gameweek 1, and a 36-hour maximum snapshot age. Optional environment variables: `DUNKEST_SEASON_ID`, `DUNKEST_GAMEWEEK`, `DUNKEST_MAX_PRELOCK_HOURS`.

The script was syntax-checked and executed on 2026-10-14. It stopped at preflight because kickoff was 126.01 hours away and explicitly confirmed that **no model run or archive was created**. This prevents another premature run from being mistaken for a certified pre-lock test.

## Prospective evaluation protocol

When the pre-lock window opens:

1. Run the new capture-and-archive script. Confirm `archive_status=certified_prelock`.
2. Freeze all strategy variants from the **same** captured market, predictions, coach projections, injury snapshot, fixture map, and transfer assumptions. Do not tune the frozen GW1 test before its cutoff.
3. After all relevant games are complete and the safe post-game retrieval time has passed, run the existing official-result collector and evaluator. Require complete player and coach outcome linkage; never impute unknown outcomes to zero.
4. Compare the risk-adjusted reference against expected-value and plusvalenza ablations on the same fixtures. A single gameweek is descriptive; do not claim statistical superiority from GW1 alone.
5. Keep each future gameweek as an immutable, fixture-linked observation. After several complete rounds, use chronological paired comparisons and uncertainty intervals for strategy selection.

## Acceptance gates

A lineup-strategy comparison is decision-grade only if:

- the frozen run and all required market snapshots are within the pre-lock window;
- every selectable player/coach is tied to the frozen eligible market;
- fixture identity and source timestamps are verified;
- player and coach realized outcomes are linked to those fixtures and hash-verified;
- unknown outcomes remain unknown;
- transfer malus/carry-over and official scoring rules are represented, or the experiment explicitly labels them as omitted;
- all strategy variants use the same candidate universe and paired target rounds;
- proxy/sensitivity metrics are reported separately from strict observed-only metrics.

## Files and verification

- Player-model metrics: `data/processed/dunkest_pdk_game_walk_forward_metrics_2020-25_v2.csv`
- Lineup proxy: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8.md`
- Historical endpoint discovery: `reports/audit/dunkest_historical_endpoint_discovery_v1.md`
- New prospective capture/archive gate: `scripts/run_and_archive_prelock_v1.sh`
- Strict immutable archiver: `scripts/archive_dunkest_prelock_run_v1.py`

No historical snapshots were fabricated. No production model was changed or tuned from proxy results. No commit or push was performed.
