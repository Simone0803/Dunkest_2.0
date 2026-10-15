# Dunkest backtest — consolidated audit

Generated (UTC): 2026-10-13T07:08:37.865060+00:00

## Status

- **Player-level historical PDK test:** summarized from saved official walk-forward artifacts.
- **NBA team-score / win-probability tests:** available on historical team game logs.
- **Complete Dunkest lineup backtest (players + coach + transfers): NOT READY.** No complete-lineup metric is reported because pre-match snapshots and linked realized results are incomplete.

## Player PDK forecast

Training corpus: 112,178 official valid player-game rows, seasons 2020/21–2025/26. Expanding-window tests use earlier seasons for training and the next season for test. The 2025/26 fold has 93,766 training rows and 18,412 test rows. The audit reports zero lag-value mismatches, zero lag-missingness mismatches and zero rows with current/future NBA history in features.

| Test season | Model | N | MAE | RMSE | Bias | R² |
|---|---|---:|---:|---:|---:|---:|
| 2022-23 | random_forest | 19165 | 7.578 | 9.842 | -0.170 | 0.441 |
| 2022-23 | ridge | 19165 | 7.628 | 9.845 | 0.104 | 0.440 |
| 2022-23 | baseline_prev10_mean | 19165 | 7.769 | 10.113 | -0.069 | 0.410 |
| 2022-23 | baseline_prev5_mean | 19165 | 7.975 | 10.440 | -0.057 | 0.371 |
| 2023-24 | random_forest | 18927 | 7.597 | 9.838 | 0.022 | 0.470 |
| 2023-24 | ridge | 18927 | 7.623 | 9.858 | 0.232 | 0.468 |
| 2023-24 | baseline_prev10_mean | 18927 | 7.765 | 10.100 | 0.048 | 0.441 |
| 2023-24 | baseline_prev5_mean | 18927 | 7.969 | 10.415 | 0.064 | 0.406 |
| 2024-25 | random_forest | 19590 | 7.589 | 9.883 | -0.114 | 0.441 |
| 2024-25 | ridge | 19590 | 7.633 | 9.928 | 0.137 | 0.435 |
| 2024-25 | baseline_prev10_mean | 19590 | 7.792 | 10.180 | -0.069 | 0.407 |
| 2024-25 | baseline_prev5_mean | 19590 | 8.003 | 10.458 | -0.023 | 0.374 |
| 2025-26 | random_forest | 18412 | 7.577 | 9.856 | -0.172 | 0.421 |
| 2025-26 | ridge | 18412 | 7.589 | 9.860 | 0.050 | 0.421 |
| 2025-26 | baseline_prev10_mean | 18412 | 7.789 | 10.154 | -0.048 | 0.386 |
| 2025-26 | baseline_prev5_mean | 18412 | 8.005 | 10.443 | -0.014 | 0.350 |

### Separately tuned candidate (2025/26 holdout)

Selected on 2022/23–2024/25 validation: **extra_trees_deep**.

| Model | N | MAE | RMSE | Bias | R² |
|---|---:|---:|---:|---:|---:|
| Tuned candidate | 18412 | 7.561 | 9.838 | -0.171 | 0.424 |
| Previous-10 baseline | 18412 | 7.789 | 10.154 | -0.048 | 0.386 |

Caveat: 2025/26 has already been examined in other project experiments; this is not a globally untouched final test.

## Rookies

The existing rookie audit covers 7,219 official rookie player-game rows from matched cohorts 2021/22–2025/26. Weighted MAE is 6.431 vs 6.714 for the previous-10 baseline across all rookie games; for the first three Dunkest games it is 4.887 vs 6.773. The cohort is name/draft-year matched and does not estimate participation probability; unobserved DNP/missing rows are not invented.

## Coach / team score forecast

- Team score model selected half-life: **15.0 games** using 2024/25 validation. On 1,230 games in 2025/26: margin MAE 11.446; home/away points MAE 10.009/9.443; win-probability Brier 0.2066; log loss 0.6014; accuracy 68.7%.
- Efficiency blend: **selected blend does not improve both Brier and log loss on validation; keep points-only baseline**. On validation, points-only Brier/log loss = 0.2098/0.6066 vs efficiency-only 0.2176/0.6257.
- PDK-derived roster-strength proxy: **do not deploy: PDK-based roster-strength proxy does not improve both Brier and log loss on validation**. Validation Brier worsens 0.2098 → 0.2102, log loss 0.6066 → 0.6076.
- Probability calibration on 2025/26: raw Brier/log loss 0.2066/0.6014; Platt 0.2067/0.6015. Calibration slightly worsens both scoring rules, so keep the raw probability setting.

These checks validate the NBA team-score/base win-probability component, not the entire Dunkest coach fantasy score using frozen coach CR, overtime, transfer penalties and a complete roster.

## Full-lineup backtest readiness

- Historical rounds scanned: 1; passing all readiness checks: **0**.
- fixture mapping: 1/1.
- roster and CR: 1/1.
- timestamped injuries: 1/1.
- fixture linked coaches: 1/1.
- player results linked: 0/1.
- coach results linked: 0/1.

The 2025/26 GW1–10 production backtest command was re-run and returned exit code 2 (`not_ready`), producing no lineup metrics. This is intentional: weekly outcome archives do not prove which CR, injuries, availability and coach prices were known before tipoff, and complete actual results are not linked to the same frozen fixture identities.

## Reproducibility and integrity

- Companion JSON records SHA-256 hashes for its key source artifacts.
- No model was refit for this summary; no production weights were changed.
- Existing data, frozen run artifacts and untracked files were preserved.
- Next end-to-end test must be prospective: freeze timestamped pre-match inputs and forecast before tipoff, then append verified player and coach outcomes.

Companion JSON: `reports/audit/dunkest_pdk_backtest_summary_20261013_v1.json`
