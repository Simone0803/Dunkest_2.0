# Coach base-score models with official Dunkest multiplier scenarios — V3

This audit applies the official coach coefficient rule to the walk-forward predictions from the base-score model and its baselines.

## Critical distinction

The coefficient table is deterministic, but the scenario CR differences below are hypothetical because historical pregame coach CR pairs are not available for 2022/23–2025/26. These results quantify sensitivity; they do not certify exact historical PDK.

## Pooled model vs previous-five baseline

Positive values in `mae_improvement_vs_prev5` mean the model has lower MAE than the previous-five baseline. All figures are scenario results, not historical-market results.

| CR difference | Coach price side | Model MAE | Previous-5 MAE | MAE improvement |
|---:|---|---:|---:|---:|
| 0 | higher_price | 16.073 | 16.894 | +0.821 |
| 0 | lower_price | 16.073 | 16.894 | +0.821 |
| 1.5 | higher_price | 15.913 | 16.707 | +0.794 |
| 1.5 | lower_price | 16.265 | 17.113 | +0.848 |
| 3 | higher_price | 15.810 | 16.584 | +0.774 |
| 3 | lower_price | 16.677 | 17.575 | +0.898 |
| 5 | higher_price | 15.735 | 16.489 | +0.754 |
| 5 | lower_price | 17.157 | 18.107 | +0.950 |
| 7 | higher_price | 15.689 | 16.424 | +0.735 |
| 7 | lower_price | 17.692 | 18.695 | +1.003 |
| 10 | higher_price | 15.679 | 16.396 | +0.716 |
| 10 | lower_price | 18.272 | 19.329 | +1.057 |
| 14 | higher_price | 15.710 | 16.409 | +0.699 |
| 14 | lower_price | 18.888 | 20.000 | +1.112 |
| 16 | higher_price | 15.816 | 16.495 | +0.679 |
| 16 | lower_price | 19.608 | 20.781 | +1.174 |

## Conclusions

- Official coefficient checks passed: 8/8.
- Methods evaluated: model_pregame_team_form, baseline_previous5_base_score, baseline_previous10_base_score, baseline_train_median.
- The base-score model is evaluated walk-forward on 2022/23, 2023/24, 2024/25 and 2025/26, using only prior-game features.
- Exact historical PDK validation still requires the two pregame CR values for each coach matchup; the official regulation alone does not supply those historical prices.
- Production model and configuration unchanged.

## Artifacts

- Metrics CSV: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v3_metrics.csv`
- Audit JSON: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v3.json`
