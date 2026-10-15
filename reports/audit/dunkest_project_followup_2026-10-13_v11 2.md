# Dunkest project follow-up — 2026-10-13 V11

## Completed: end-to-end lineup proxy ablation, matchup V2 vs rest/schedule V6

Created and executed:
- `scripts/backtest_dunkest_historical_lineups_rest_schedule_v1.py`
- `scripts/audit_dunkest_historical_lineups_rest_schedule_paired_bootstrap_v1.py`

Artifacts:
- `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1.md`
- `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_metrics.csv`
- `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_rounds.csv`
- `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_lineups.csv`
- `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1.json`
- `reports/audit/dunkest_historical_lineups_rest_schedule_paired_bootstrap_20261013_v1.md`
- `reports/audit/dunkest_historical_lineups_rest_schedule_paired_bootstrap_20261013_v1.csv`
- `reports/audit/dunkest_historical_lineups_rest_schedule_paired_bootstrap_20261013_v1.json`

### Protocol

Compared the expanded-matchup model (V2) with V6 (same features plus seven past-only rest/congestion features). Both models were trained on identical earlier seasons and optimized over the same candidate pool and target rounds. Candidate team/role/CR are carried from the latest archived row strictly before the target round; target-round PDK is used only for realized scoring. Candidate-team assignment no longer uses the target-round player outcome row. The opponent schedule is reconstructed from high-confidence round-date mapping and NBA team logs; no target PDK is a predictor.

This remains a restricted historical proxy, not a complete market backtest: only players observed earlier in the season can be candidates, target-row absence is treated as zero realized PDK, coach CR is fixed at 10 with neutral-credit coach base score, transfer malus is zero, and the optimizer has a one-second time limit.

### Results

409 paired rounds were evaluated (132 in 2023/24, 138 in 2024/25, 139 in 2022/23); 49 rounds failed optimization and 6 had too few candidates. Mean target-outcome player coverage among candidates was 94.9–95.2%.

| Held-out season | Mean V2 realized team score | Mean V6 realized team score | V6 − V2 |
|---|---:|---:|---:|
| 2022/23 | 150.331 | 149.928 | -0.403 |
| 2023/24 | 163.116 | 164.843 | +1.727 |
| 2024/25 | 166.380 | 169.748 | +3.368 |
| Macro-season | 159.942 | 161.507 | +1.564 |

A paired bootstrap of 10,000 replicates resampled whole rounds within held-out seasons. Macro-season 95% interval for V6 minus V2: **[-1.950, +5.080]** realized team points per round; 81.0% of bootstrap replicates were positive. V6's round win rate was 49.2% pooled, with a median round delta of 0.0. Thus the apparent average gain is unstable and is not supported by a confidence interval excluding zero.

### Decision

**Do not promote V6 or change production weights.** Player-level MAE improved slightly, but this restricted lineup proxy does not demonstrate a reliable lineup gain. The historical lineup result is dominated by incomplete market/coach/transfer assumptions, and results vary by season.

## Existing issues that remain materially relevant

- Certified official PDK target labels begin in 2020/21; 2018/19 and 2019/20 rows in the archive have invalid official-game flags. Use those earlier years as NBA history only unless certified PDK labels are recovered.
- 2025/26 has already been examined in earlier tuning/calibration experiments; do not describe it as an untouched project-wide holdout or retune against it.
- The production opening-round trainer still fits its main model on the prior season only. A separate multi-season historical PDK model is blended into predictions, but its feature schema is different. Any trainer change must be supported by chronological out-of-fold comparison and integration tests.
- The primary feature pipeline can retain proxy-derived rolling PDK features even when official labels are selected as the supervised target. Measure this provenance mismatch before integration.
- Participation probability is not yet validated from labels that distinguish DNP/zero-minute outcomes from missing rows.
- Exact historical coach credit multipliers and transfer malus cannot be certified without archived coach prices and carried rosters.
- The prospective 2026/27 GW1 run remains frozen until 2026-10-23 12:00 UTC. Do not tune on that holdout.

## Next priority

Continue with the most decision-relevant unresolved task: evaluate the main model's multi-season training scope and target/feature PDK provenance in strict expanding-origin folds. Preserve the current production path until a fair out-of-sample comparison and integration tests show an improvement. Then audit minutes/participation labels and optimizer/coach sensitivity. Do not invent missing pre-lock evidence.
