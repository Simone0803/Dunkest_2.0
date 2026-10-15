# Dunkest project follow-up — 2026-10-13 V10

## Completed in this iteration

Added and ran a new, isolated walk-forward ablation for past-only rest and schedule features.

Scripts:
- `scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v6_rest_schedule.py`
- `scripts/audit_dunkest_rest_schedule_paired_bootstrap_v1.py`

Primary report:
- `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule.md`
- `reports/audit/dunkest_rest_schedule_paired_bootstrap_20261013_v1.md`

The experiment compares the existing expanded-matchup model against the same model with seven additional numeric inputs: own-team and opponent days since the last game, games in the prior seven days for both teams, back-to-back flags for both teams, and rest-day advantage. Rest features are derived from team-game logs using dates strictly earlier than the target date. Since the archive is date-only, all games on the target date are excluded.

## Results

Expanding-origin held-out seasons: 2022/23, 2023/24, 2024/25. Total paired sample: 55,565 player-round predictions across 467 season-week-round clusters.

| Metric | Expanded matchup V2 | V6 + rest/schedule | Change |
|---|---:|---:|---:|
| Pooled MAE | 7.50275 | 7.47766 | -0.02509 |
| Pooled RMSE | 9.79656 | 9.75439 | -0.04217 |
| Pooled bias | -0.62246 | -0.56334 | bias closer to zero |

The paired bootstrap resampled complete round clusters within each held-out season (10,000 replicates). Macro-season delta MAE, V6 minus baseline, was -0.02513 with a 95% interval of [-0.03388, -0.01679]; all bootstrap estimates were below zero. The per-season point estimates were also negative:
- 2022/23: -0.02670 MAE
- 2023/24: -0.02798 MAE
- 2024/25: -0.02072 MAE

This is consistent, but small, player-level improvement. It does not establish that an optimized lineup scores better, and must not be interpreted as proof that a production model should change.

## Decision and constraints

- Keep the V6 rest/schedule model experimental; do not change production weights, configuration, or lineup optimizer based on this result alone.
- Continue to treat historical player-round data as outcome archives, not as a complete timestamped pre-lock candidate universe.
- Exact historical coach credit-adjusted scores still need authentic historical coach CRs or an independently validated reconstruction.
- Keep the 2026/27 prospective GW1 snapshots frozen. Do not evaluate or tune against that prospective holdout before the existing cutoff, 2026-10-23 12:00 UTC.
- Do not commit or push changes. Preserve all existing local modifications and untracked artifacts.

## Next work

Prioritize an end-to-end lineup-level test before adding more player features. Use only a verified candidate universe and pre-lock inputs, include coach and transfer-malus logic where historically supportable, and compare baseline versus V6 on identical rounds with paired round-level uncertainty. If historical inputs are incomplete, report readiness/coverage rather than manufacture a lineup score. The prospective GW1 run remains a later independent check, not a tuning set.
