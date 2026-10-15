# Dunkest coach score forecast: direct model vs pregame Monte Carlo — V4

## Method

- Evaluated 4,920 games / 9,840 team-game coach outcomes across 2022/23–2025/26.
- Team-point forecasts use half-life 15, selected on 2024/25 validation; 2025/26 remains the final holdout.
- Monte Carlo uses 8,192 draws per game, team-score SDs and score correlation estimated strictly from prior dates, plus prior-only overtime frequency.
- The score simulation imports the same overtime helper as the production coach model; V3's separate simulator is retained only as an earlier experiment.
- Applies the official coach scoring rules to simulated outcomes with equal CR=10 on both sides, isolating the base score.
- Direct model and previous-5/previous-10 baselines are joined on season + NBA game ID + team.

## Pooled metrics

| Method | N | MAE | RMSE | Bias |
|---|---:|---:|---:|---:|
| monte_carlo_team_score_distribution | 9,840 | 15.202 | 17.461 | +0.135 |
| direct_base_score_model | 9,840 | 16.073 | 17.934 | +0.001 |
| baseline_previous5 | 9,840 | 16.894 | 19.888 | +0.000 |
| baseline_previous10 | 9,840 | 16.596 | 19.098 | -0.001 |

## Interpretation

This is the key comparison for deciding whether the rule-aware score distribution adds value beyond a direct score model. The result is still a neutral-credit base-score comparison, not exact historical PDK. No production model or config is changed.

## Artifacts

- Predictions: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v4_predictions.csv`
- Metrics: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v4_metrics.csv`
- Audit JSON: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v4.json`
