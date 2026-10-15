# Score-band uncertainty calibration — implementation V1

## Change

The production predictor now learns residual P10/P50/P90 quantiles separately for forecast-score bands (`<5`, `5–10`, `10–15`, `15–20`, `20–25`, `25+`) from its strictly cross-fitted historical predictions. Sparse band quantiles are shrunk toward pooled residual quantiles with `alpha = n / (n + 1000)`. At inference, the conditional score forecast chooses the matching quantiles; unknown or missing bands fall back to pooled calibration.

The residual convention is `actual PDK − predicted PDK`, consistent with the quantile utility. Empirical residual quantiles remain in PDK units and are not rescaled by player volatility. The separate play-probability mixture is retained, and all quantile outputs remain ordered.

## External past-only evidence

The new production-adapter OOF audit trained score-band quantiles only on earlier seasons and evaluated the following seasons, excluding 2025/26 and leaving the frozen 2026/27 GW1 untouched.

| Test season | Calibration | Central 80% coverage | Mean interval width | Median-adjusted MAE |
|---|---|---:|---:|---:|
| 2023/24 | Pooled | 80.06% | 24.458 | 7.509 |
| 2023/24 | Score-band | 80.83% | 24.303 | 7.489 |
| 2024/25 | Pooled | 80.07% | 24.413 | 7.565 |
| 2024/25 | Score-band | 80.75% | 24.261 | 7.559 |

The score-band approach modestly improves both marginal tail coverage and central coverage while slightly narrowing the interval in both folds. This supports the implementation as a bounded uncertainty-calibration improvement; it does not certify risk-adjusted lineup superiority or prove that actual high-score tail error has been solved.

## Safeguards

- Calibration uses only cross-fitted residuals from available training history.
- No target-season actual labels are used at inference.
- Pooled quantiles remain the fallback for sparse/missing bands.
- The optimizer objective, risk penalty, availability policy, model weights, and plusvalenza weight were not changed.
- 2025/26 remains excluded from this new calibration experiment because it has been examined in prior project work; 2026/27 GW1 remains frozen until 2026-10-23 12:00 UTC.

## Verification

- Added unit tests for row-specific quantiles, index alignment, residual sign and band lookup.
- Full test suite: 381 passed.
- `git diff --check`: passed.
- No commit or push.

## Artifacts

- `scripts/audit_dunkest_score_band_interval_calibration_v1.py`
- `reports/audit/dunkest_score_band_interval_calibration_20261014_v1.md`
- `reports/audit/dunkest_score_band_interval_calibration_20261014_v1_metrics.csv`
- `reports/audit/dunkest_score_band_interval_calibration_20261014_v1_cohorts.csv`

## Production-path smoke test

Trained the actual opening-round multi-season model on 93,766 certified rows from 2020/21–2024/25. It produced 38,517 cross-fitted calibration predictions, populated all six score bands, and returned finite P10/P50/P90 residual quantiles for a 200-row prediction smoke test. This verifies the integration path and calibration lookup, not forecast quality on an independent test set.
