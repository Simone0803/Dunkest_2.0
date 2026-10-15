# Official vs proxy PDK history features — paired ablation

- Run date: 2026-10-14
- Target: verified official Dunkest PDK
- Rows scored: 7,295 OOF rows per candidate
- Data: 2025/26 season, already examined in earlier project experiments
- Scope: exploratory ablation, not a pristine final holdout

## Method

Two otherwise identical model runs used the same player-game rows and official PDK targets. The only change was the source of lagged PDK history features:

- Official history: use PDK_OFFICIAL_VALID where verified; fall back to proxy PDK only when an official label is missing.
- Proxy-only history: use the original NBA-boxscore PDK proxy for all history.

Schedule, matchup and injury features were disabled to isolate this change. The model family and expanding-date validation procedure were unchanged. No production model weights were modified.

## Results

| Metric | Official history | Proxy-only | Difference |
|---|---:|---:|---:|
| MAE | 7.64949 | 7.65708 | -0.00759 |
| RMSE | 9.92350 | 9.93198 | -0.00848 |
| Bias (prediction − actual) | -0.07480 | -0.07121 | -0.00360 |
| MAE, actual PDK ≥25 | 12.28122 | 12.31591 | -0.03468 |
| MAE, actual PDK ≥30 | 14.91594 | 14.94235 | -0.02641 |

The official-history version is slightly better on overall MAE/RMSE and both high-score cohorts. The improvement is real in this paired run but small; it should not be presented as a large accuracy gain.

## Data quality

The official overlay matched 24,098 of 24,146 player-game rows; 48 rows were unmatched and retained without official labels. The number of OOF rows scored is lower than the full season because the first temporal fold is used for tuning and excluded from the later OOF calibration/weighting sample.

## Limitations

- The 2025/26 season has already been examined elsewhere in this project; this is not an untouched holdout.
- The ablation disables schedule, matchup and injury features; the result isolates PDK-history provenance rather than the full production model.
- The feature-source change does not solve the larger limitation that the primary GW1 trainer is prior-season-only.

## Decision

Keep the official-history preference: it is more faithful to the target definition and shows a small consistent improvement. Do not change ensemble weights or claim a major accuracy improvement based on this test alone. Continue with multi-season, expanding-origin validation and a future untouched period.

## Reproducibility

- Script: scripts/audit_dunkest_official_vs_proxy_history_features_v1.py
- Metrics JSON: reports/audit/dunkest_official_vs_proxy_pdk_history_features_20261014_v1.json
