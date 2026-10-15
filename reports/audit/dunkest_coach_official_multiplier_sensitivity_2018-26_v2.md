# Coach base-score models with official Dunkest multiplier scenarios — V2

This audit applies the official coach coefficient rule to the walk-forward predictions from the base-score model and its baselines.

## Critical distinction

The coefficient table is deterministic, but the scenario CR differences below are hypothetical because historical pregame coach CR pairs are not available for 2022/23–2025/26. These results quantify sensitivity; they do not certify exact historical PDK.

## Pooled model vs previous-five baseline

Positive values in `mae_improvement_vs_prev5` mean the model has lower MAE than the previous-five baseline. All figures are scenario results, not historical-market results.

| CR difference | Coach price side | Model MAE | Previous-5 MAE | MAE improvement |
|---:|---|---:|---:|---:|
| 0 | higher_price | 16.073 | 16.894 | +0.821 |
| 0 | lower_price | 16.073 | 16.894 | +0.821 |
| 1.5 | higher_price | 15.269 | 16.049 | +0.780 |
| 1.5 | lower_price | 16.877 | 17.739 | +0.862 |
| 3 | higher_price | 14.627 | 15.373 | +0.747 |
| 3 | lower_price | 18.323 | 19.259 | +0.936 |
| 5 | higher_price | 13.984 | 14.698 | +0.714 |
| 5 | lower_price | 19.770 | 20.779 | +1.010 |
| 7 | higher_price | 13.341 | 14.022 | +0.681 |
| 7 | lower_price | 21.217 | 22.300 | +1.083 |
| 10 | higher_price | 12.698 | 13.346 | +0.648 |
| 10 | lower_price | 22.663 | 23.820 | +1.157 |
| 14 | higher_price | 12.055 | 12.670 | +0.616 |
| 14 | lower_price | 24.110 | 25.341 | +1.231 |
| 16 | higher_price | 11.251 | 11.826 | +0.575 |
| 16 | lower_price | 25.717 | 27.030 | +1.313 |

## Conclusions

- Official coefficient checks passed: 8/8.
- Methods evaluated: model_pregame_team_form, baseline_previous5_base_score, baseline_previous10_base_score, baseline_train_median.
- The base-score model is evaluated walk-forward on 2022/23, 2023/24, 2024/25 and 2025/26, using only prior-game features.
- Exact historical PDK validation still requires the two pregame CR values for each coach matchup; the official regulation alone does not supply those historical prices.
- Production model and configuration unchanged.

## Artifacts

- Metrics CSV: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v2_metrics.csv`
- Audit JSON: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v2.json`
