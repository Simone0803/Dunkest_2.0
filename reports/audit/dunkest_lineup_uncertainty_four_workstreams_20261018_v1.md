# Dunkest lineup uncertainty — four-workstream historical audit

Generated UTC: 2026-10-18T13:25:36.775771+00:00

## Scope and leakage controls

- Source: `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v2_predictions.csv`; current production ensemble OOS predictions only.
- Interval calibration tests 2023/24 and 2024/25 using strictly earlier seasons only.
- 2025/26 and the frozen 2026/27 GW1 prospective bundle are excluded from calibration and tuning.
- No production configuration, weights, model, or lineup selection was changed.

## 1. Past-only quantile calibration

Residual = forecast − actual. For an 80% central interval, central coverage should be near 0.80 and marginal lower/upper coverage near 0.90. Width is only compared at acceptable coverage.

| Test season | Method | Forecast band | N | Lower coverage | Upper coverage | Central 80% | Mean width | Median-offset MAE |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 2023-24 | pooled_past_only | all | 18927 | 0.903 | 0.898 | 0.801 | 24.02 | 7.429 |
| 2023-24 | score_band_shrunk_past_only | <5 | 1574 | 0.995 | 0.950 | 0.945 | 18.42 | 3.737 |
| 2023-24 | score_band_shrunk_past_only | 5-10 | 4156 | 0.926 | 0.912 | 0.838 | 18.90 | 5.493 |
| 2023-24 | score_band_shrunk_past_only | 10-15 | 4474 | 0.908 | 0.900 | 0.808 | 22.79 | 7.024 |
| 2023-24 | score_band_shrunk_past_only | 15-20 | 3317 | 0.890 | 0.889 | 0.779 | 25.88 | 8.361 |
| 2023-24 | score_band_shrunk_past_only | 20-25 | 2257 | 0.889 | 0.882 | 0.771 | 27.30 | 9.104 |
| 2023-24 | score_band_shrunk_past_only | 25+ | 3149 | 0.882 | 0.883 | 0.765 | 30.19 | 10.117 |
| 2024-25 | pooled_past_only | all | 19590 | 0.896 | 0.905 | 0.801 | 24.03 | 7.459 |
| 2024-25 | score_band_shrunk_past_only | <5 | 1720 | 0.976 | 0.933 | 0.909 | 15.51 | 3.693 |
| 2024-25 | score_band_shrunk_past_only | 5-10 | 3942 | 0.913 | 0.901 | 0.814 | 18.23 | 5.704 |
| 2024-25 | score_band_shrunk_past_only | 10-15 | 4906 | 0.913 | 0.897 | 0.810 | 22.67 | 7.126 |
| 2024-25 | score_band_shrunk_past_only | 15-20 | 3504 | 0.891 | 0.904 | 0.795 | 26.31 | 8.196 |
| 2024-25 | score_band_shrunk_past_only | 20-25 | 2215 | 0.873 | 0.905 | 0.777 | 28.04 | 8.984 |
| 2024-25 | score_band_shrunk_past_only | 25+ | 3303 | 0.879 | 0.897 | 0.777 | 31.29 | 10.167 |

## 2. Same-game residual dependence

This is an ANOVA method-of-moments estimate of shared game-level residual dependence from out-of-sample player forecasts. It is diagnostic, not a fitted production correlation coefficient.

| Season | Games (>=8 rows) | Player rows | Avg players/game | SD game-mean residual | Within-game residual SD | Approx ICC | Bootstrap 95% CI game-mean bias |
|---|---:|---:|---:|---:|---:|---:|---|
| 2022-23 | 1042 | 19165 | 18.4 | 2.582 | 9.719 | 0.0072 | [-0.259, 0.049] |
| 2023-24 | 1012 | 18920 | 18.7 | 2.487 | 9.715 | 0.0057 | [-0.470, -0.174] |
| 2024-25 | 1036 | 19576 | 18.9 | 2.613 | 9.734 | 0.0115 | [-0.433, -0.121] |

## 3. Risk-aware lineup objective

**Not certified / not tuned.** Available historical archives do not establish authentic pre-lock roster, credits, injuries, fixture-linked coach market and realized scores for enough complete rounds. Tuning `risk_lambda`, correlation, or CVaR on reconstructed lineups would select against proxy labels and could introduce look-ahead bias. Keep current production setting until certified lineup-level walk-forward evidence exists.

## 4. Minutes, role and participation

The prior walk-forward minutes audit reports HGB MAE 4.983 minutes vs 5.127 for the previous-five baseline over 57,682 player-games, but the low-history and zero-minute cohorts remain difficult. Prior downstream tests did not justify directly scaling PDK by the minutes model. Retain it as an auxiliary/shadow estimate; do not increase its production weight without paired PDK and lineup-level gains.

## Decision

- Run the score-band calibration as a challenger only; promote only if repeated outer-fold coverage is near nominal and intervals are meaningfully tighter without subgroup failures.
- Use the measured game-cluster diagnostics to design a future joint scenario model, not to hardcode a correlation.
- Do not change `risk_lambda` without certified lineup backtests.
- Keep production predictions and the frozen GW1 bundle unchanged.

## Artifacts
- `reports/audit/dunkest_lineup_uncertainty_four_workstreams_20261018_v1.json`
- `reports/audit/dunkest_lineup_uncertainty_four_workstreams_20261018_v1_interval_metrics.csv`
- `reports/audit/dunkest_lineup_uncertainty_four_workstreams_20261018_v1_game_cluster_metrics.csv`

## Reproduction
```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_lineup_uncertainty_four_workstreams_20261018_v1.py
```
