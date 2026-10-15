# Dunkest coach score forecast: direct model vs pregame Monte Carlo — V3

## Method

- Evaluated 4,920 games / 9,840 team-game coach outcomes across 2022/23–2025/26.
- Team-point forecast uses half-life 15, selected on 2024/25 validation; 2025/26 is reported as the final holdout.
- 8,192 Monte Carlo draws per game. Team-score volatility, score correlation and overtime probability are initialized from all NBA games strictly before the first test date, then updated only after every forecast on each date has been produced.
- Official Dunkest coach scoring rules applied with equal CR=10 for both coaches to isolate the neutral-credit base score.
- Direct model and previous-5/previous-10 baselines joined by season + NBA game ID + team.
- The forecasts are generated before same-date outcomes enter the rolling history. No same-day results enter pregame features.

## Pooled metrics

| Method | N | MAE | RMSE | Bias |
|---|---:|---:|---:|---:|
| monte_carlo_team_score_distribution | 9,840 | 15.184 | 17.459 | -0.130 |
| direct_base_score_model | 9,840 | 16.073 | 17.934 | +0.001 |
| baseline_previous5 | 9,840 | 16.894 | 19.888 | +0.000 |
| baseline_previous10 | 9,840 | 16.596 | 19.098 | -0.001 |

## Per-season MAE

| Test season | Monte Carlo | Direct coach-score model | Previous-10 baseline |
|---|---:|---:|---:|
| 2022-23 | 15.423 | 16.127 | 16.637 |
| 2023-24 | 15.224 | 16.250 | 16.607 |
| 2024-25 | 15.038 | 16.000 | 16.491 |
| 2025-26 | 15.051 | 15.915 | 16.649 |
| pooled_2022-26 | 15.184 | 16.073 | 16.596 |

## Paired uncertainty analysis

A 10,000-replicate game-cluster bootstrap keeps both opposing coach outcomes together. The pooled interval is stratified by season. Negative differences favour Monte Carlo.

| Comparator | MAE difference (MC − comparator) | 95% bootstrap interval | Games where MC has lower mean absolute error |
|---|---:|---:|---:|
| direct | -0.889 | [-1.019, -0.757] | 58.6% |
| prev10 | -1.412 | [-1.548, -1.278] | 62.2% |

## Interpretation

- On the 2025/26 holdout, Monte Carlo MAE is 15.051 vs 15.915 for the direct model and 16.649 for the previous-10 baseline. The holdout was not used to choose the 15-game half-life.
- Pooled Monte Carlo MAE is about 5.5% lower than the direct coach-score model and 8.5% lower than the previous-10 baseline. The paired bootstrap interval is below zero for both comparisons.
- This supports the rule-aware Monte Carlo approach for predicting neutral-credit base coach score. It does not validate exact historical price-adjusted coach PDK because historical CR pairs are missing.
- The production coach predictor already uses a Monte Carlo rule-aware score distribution. This experiment does not justify changing production coefficients or the roster-strength proxy; that proxy did not improve both Brier and log loss.
- No production model or configuration was changed.

## Artifacts

- Predictions: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v3_predictions.csv`
- Metrics: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v3_metrics.csv`
- Audit JSON: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v3.json`
- Paired bootstrap report: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v2.md`
