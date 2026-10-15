# V9 walk-forward residual-segment audit

Created UTC: 2026-10-13T12:22:10.551464+00:00

## Scope

Descriptive audit of persisted V9 expanding-origin OOF predictions. No refitting, model selection, or production changes; prospective 2026/27 GW1 holdout was not read.

Source rows: 285,304; unique player-round keys: 57,662.

## Overall paired comparisons

| comparison                                | n_common | mae_a  | mae_b  | delta_mae_b_minus_a | ci95_low | ci95_high | rmse_a | rmse_b |
| ----------------------------------------- | -------- | ------ | ------ | ------------------- | -------- | --------- | ------ | ------ |
| rest_schedule_minus_expanded_matchup      | 57662    | 7.4754 | 7.4534 | -0.022              | -0.0314  | -0.0122   | 9.7622 | 9.724  |
| expanded_matchup_minus_previous5_baseline | 56159    | 7.9693 | 7.4303 | -0.539              | -0.5853  | -0.4966   | 10.466 | 9.6863 |
| rest_schedule_minus_previous5_baseline    | 56159    | 7.9693 | 7.4217 | -0.5475             | -0.592   | -0.5014   | 10.466 | 9.68   |

Delta and confidence interval are for MAE(model B) minus MAE(model A); negative favors B. Bootstrap resamples historical round clusters within each season.

## By held-out season

| comparison                                | season  | n_common | mae_a  | mae_b  | delta_mae_b_minus_a |
| ----------------------------------------- | ------- | -------- | ------ | ------ | ------------------- |
| rest_schedule_minus_expanded_matchup      | 2022-23 | 19155    | 7.4559 | 7.433  | -0.0229             |
| rest_schedule_minus_expanded_matchup      | 2023-24 | 18918    | 7.4944 | 7.4638 | -0.0306             |
| rest_schedule_minus_expanded_matchup      | 2024-25 | 19589    | 7.476  | 7.4632 | -0.0128             |
| expanded_matchup_minus_previous5_baseline | 2022-23 | 18673    | 7.9619 | 7.404  | -0.5579             |
| expanded_matchup_minus_previous5_baseline | 2023-24 | 18406    | 7.9486 | 7.4457 | -0.503              |
| expanded_matchup_minus_previous5_baseline | 2024-25 | 19080    | 7.9964 | 7.4411 | -0.5553             |
| rest_schedule_minus_previous5_baseline    | 2022-23 | 18673    | 7.9619 | 7.3972 | -0.5647             |
| rest_schedule_minus_previous5_baseline    | 2023-24 | 18406    | 7.9486 | 7.4346 | -0.514              |
| rest_schedule_minus_previous5_baseline    | 2024-25 | 19080    | 7.9964 | 7.4333 | -0.5631             |

## Rest/schedule effect by lagged market segment

| dimension          | segment        | n     | mae_expanded_matchup | mae_rest_schedule | delta_mae_rest_minus_matchup | ci95_low | ci95_high |
| ------------------ | -------------- | ----- | -------------------- | ----------------- | ---------------------------- | -------- | --------- |
| lagged_cr_quartile | (3.999, 4.6]   | 14725 | 5.2714               | 5.2689            | -0.0025                      | -0.0111  | 0.006     |
| lagged_cr_quartile | (4.6, 7.0]     | 13386 | 6.8169               | 6.804             | -0.0129                      | -0.0226  | -0.003    |
| lagged_cr_quartile | (7.0, 11.0]    | 14201 | 8.0493               | 8.0466            | -0.0027                      | -0.0133  | 0.0074    |
| lagged_cr_quartile | (11.0, 29.2]   | 13847 | 9.6841               | 9.6673            | -0.0168                      | -0.0307  | -0.0029   |
| lag1_pdk_quartile  | (-12.251, 5.5] | 14164 | 5.6756               | 5.6704            | -0.0052                      | -0.0135  | 0.0033    |
| lag1_pdk_quartile  | (5.5, 13.5]    | 14137 | 7.0097               | 6.9961            | -0.0136                      | -0.0236  | -0.0039   |
| lag1_pdk_quartile  | (13.5, 23.75]  | 13912 | 7.9152               | 7.9042            | -0.0111                      | -0.0223  | -0.0005   |
| lag1_pdk_quartile  | (23.75, 92.4]  | 13946 | 9.1549               | 9.1506            | -0.0044                      | -0.0171  | 0.0098    |

Negative delta favors adding rest/schedule features. Segment intervals are exploratory and not multiplicity-adjusted.

## Absolute-error deciles for rest/schedule model

| absolute_error_decile | n    | mean_abs_error | mean_signed_error | mean_actual_pdk | mean_predicted_pdk | mean_lagged_cr | mean_lag1_pdk |
| --------------------- | ---- | -------------- | ----------------- | --------------- | ------------------ | -------------- | ------------- |
| 1                     | 5767 | 0.568          | 0.0281            | 13.4881         | 13.5163            | 7.5021         | 13.8557       |
| 2                     | 5766 | 1.7272         | 0.1905            | 13.2248         | 13.4152            | 7.4663         | 13.7782       |
| 3                     | 5766 | 2.8756         | 0.4801            | 12.529          | 13.0091            | 7.3127         | 13.3209       |
| 4                     | 5766 | 4.0214         | 0.8946            | 12.4805         | 13.3751            | 7.4751         | 13.6591       |
| 5                     | 5766 | 5.2343         | 1.3235            | 12.5043         | 13.8277            | 7.6064         | 14.3394       |
| 6                     | 5766 | 6.5954         | 1.3768            | 13.1205         | 14.4974            | 7.8753         | 14.8687       |
| 7                     | 5766 | 8.2171         | 1.3439            | 14.379          | 15.7229            | 8.3702         | 16.1942       |
| 8                     | 5766 | 10.3565        | 0.6064            | 16.4662         | 17.0725            | 9.0197         | 18.0012       |
| 9                     | 5766 | 13.5239        | -0.9599           | 19.6273         | 18.6675            | 9.8674         | 19.5896       |
| 10                    | 5767 | 21.4131        | -10.9204          | 31.6236         | 20.7032            | 11.0146        | 22.2431       |

## Interpretation guardrails

- Diagnostics use saved expanding-origin out-of-fold predictions only; no model fitting, feature selection, or hyperparameter tuning is performed.
- Segments use lagged CR and prior-round PDK only; these are descriptive strata, not causal explanations.
- The historical source does not provide a complete pre-lock market snapshot or reliable DNP/OUT labels.
- No production code/configuration or frozen 2026/27 GW1 holdout was modified.

## Artifacts

- `reports/audit/dunkest_v9_residual_segments_20261013_v1_overall.csv`
- `reports/audit/dunkest_v9_residual_segments_20261013_v1_by_season.csv`
- `reports/audit/dunkest_v9_residual_segments_20261013_v1_market_segments.csv`
- `reports/audit/dunkest_v9_residual_segments_20261013_v1_error_deciles.csv`
- `reports/audit/dunkest_v9_residual_segments_20261013_v1.md`
- `reports/audit/dunkest_v9_residual_segments_20261013_v1.json`
