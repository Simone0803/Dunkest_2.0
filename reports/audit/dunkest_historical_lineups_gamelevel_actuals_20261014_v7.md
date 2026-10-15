# Dunkest historical lineup experiment with calibrated zero-inclusive lineups — V7

Generated (UTC): 2026-10-14T13:15:23.690382+00:00

V7 fixes the V3 candidate-slate bug: target teams/opponents are rebuilt from the full NBA schedule for the target season/date, not inferred from sparse teams in the Dunkest outcome table. Candidate team assignment uses the latest strictly pre-target linked NBA team where available. Training remains past-only.

## Method

For each historical target round, training predictors are built from the player's latest archived row strictly before that target round. Training uses a reconstructed candidate universe: when a prior-observed player is assigned to a team on the target slate but has no player-week-round outcome row, the target is set to 0 in this explicit proxy. Both the model and previous-five baseline are calibrated with role-by-history residuals from expanding-season OOS predictions before optimization. Realized scores are joined only after selection from the official player-week-round archive; absent rows are zero only in the proxy scenario.

## Game-level reconstruction validation

- Historical weekly rows compared: 93,734
- Rows matching weekly PDK within 0.02 points: 93,728 (99.994%)
- Mean absolute difference: 0.00149 PDK

The optimizer uses the repository roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model. The historical candidate pool, prices and availability remain proxies; missing player scores remain unknown and exclude a round from strict paired comparisons.

## Strict observed-only results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24                 2                      229.112500                         214.667500                        14.445000                             14.445                    1.000000            249.000000                            0.819767                     0.918050
        9         2022-23                 6                      175.576667                         191.994167                       -16.417500                            -18.525                    0.166667            199.833333                            0.700317                     0.986369
   POOLED 2022-23–2024-25                 8                      188.960625                         197.662500                        -8.701875                            -13.600                    0.375000            212.125000                            0.730180                     0.969289

## Player forecast calibration (zero-inclusive proxy target)

           forecast      n      mae      rmse  bias_pred_minus_actual  observations_with_zero_proxy
          model_raw 109467 6.804401  9.962823               -0.218828                         55133
   model_calibrated 109467 6.712798  9.976585               -0.560609                         55133
       baseline_raw 109467 9.670876 13.134848                5.429811                         55133
baseline_calibrated 109467 8.577887 11.905247                0.178658                         55133

Calibration uses only expanding-season OOS residuals. These metrics use the explicit zero-for-missing target and must be interpreted as proxy calibration, not official observed-only calibration.

## Explicit proxy scenario: missing player PDK set to zero

This sensitivity scenario assumes a candidate absent from the historical Dunkest player-week-round outcome archive scores 0. It is an explicit proxy for an unobserved outcome, not a certified actual. Interpret its strategy comparison as exploratory only.

season_id          season  rounds_evaluated_proxy  mean_model_realized_team_score_proxy  mean_baseline_realized_team_score_proxy  mean_delta_model_minus_baseline_proxy  median_delta_model_minus_baseline_proxy  model_win_rate_vs_baseline_proxy  mean_candidate_count
       13         2023-24                     147                            171.891837                               120.446735                              51.445102                                  52.6050                          0.809524            245.965986
       19         2024-25                     152                            167.449934                               122.418849                              45.031086                                  44.5425                          0.776316            245.085526
        9         2022-23                     159                            148.619119                               112.971226                              35.647893                                  27.0000                          0.685535            226.364780
   POOLED 2022-23–2024-25                     458                            162.338275                               118.506026                              43.832249                                  41.9250                          0.755459            238.868996

## Paired uncertainty

- Strict observed-only estimates use only rounds with complete observed player and coach outcomes; proxy estimates are reported separately and must not be interpreted as certified results.

## Selection-conditioned calibration

- Model: mean expected team score 172.72, realized 195.79 (optimism gap -23.072)
- Raw previous-five baseline strict: expected 254.57, realized 197.60 (gap 56.970)
- Model proxy: expected 169.59, realized 162.34 (gap 7.250)
- Baseline proxy: expected 229.02, realized 118.51 (gap 110.516)
Both strategies are now calibrated with past-only role/history residuals. The comparison remains conditional on the zero-for-missing training/evaluation proxy and incomplete historical market/availability snapshots; it is not a production-superiority claim.

## Coverage

- Round outcomes: {'selected_actuals_incomplete': 450, 'evaluated': 8, 'candidate_pool_too_small': 3, 'optimization_failed': 3}
- Optimized lineup records: 916

## Critical caveats

The candidate universe is reconstructed from prior-season-round observations and the latest linked NBA team available before each target round. Players never observed earlier in the season, late additions, and traded players without a prior linked appearance for the new team may be missing or misassigned. CR and role are lagged proxies, not certified pre-lock market state.

Historical availability is not timestamped; p_play=1 is an eligibility proxy, not verified availability. A selected lineup is included in paired realized-score metrics only when all selected player scores and the coach base score are observed. Missing scores are not imputed to zero.

Coach prices are missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is zero because historical carried rosters are not archived. This compares fresh independent round lineups, not a sequential roster with transfers. The full slate comes from NBA team-game logs, but this remains a reconstructed proxy rather than a certified historical Dunkest market backtest.

Production model/configuration remains unchanged.

## Artifacts

- Strict observed-only metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_metrics.csv`
- Explicit proxy metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_proxy_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7.json`


## Past-only player forecast calibration

| Forecast | MAE | RMSE | Bias (prediction − proxy actual) |
|---|---:|---:|---:|
| Model raw | 6.804 | 9.963 | -0.219 |
| Model role/history calibrated | 6.713 | 9.977 | -0.561 |
| Previous-five raw | 9.671 | 13.135 | +5.430 |
| Previous-five role/history calibrated | 8.578 | 11.905 | +0.179 |

Calibration improves the baseline materially. For the model, MAE improves slightly but RMSE and bias worsen slightly; this is a trade-off, not a universal improvement. These metrics use the zero-inclusive proxy target.

## Paired strategy comparison

- V7 calibrated zero-inclusive model vs V7 calibrated previous-five baseline: **+43.83 PDK per round**, 75.5% round win rate, season-stratified paired bootstrap 95% CI **[+38.61, +49.05]**, 458 paired rounds.
- V7 model vs V6 observed-row-trained raw model, same 458 rounds: **+26.24 PDK per round**, model wins 68.8%; paired bootstrap 95% CI **[+21.24, +31.28]**.
- V7 calibrated previous-five baseline vs V6 raw baseline: **−2.12 PDK per round**, 95% CI **[−3.76, −0.50]**.

All three comparisons above use the explicit zero-for-missing proxy for realized scores. They quantify performance under that assumption, not certified official-score superiority.

## Strict observed-only cross-check

On the exact rounds where both V6 and V7 have complete observed scores for both strategies, there are only **5 paired rounds**. In that tiny sample, V7 model minus V7 baseline averages **−7.03 PDK**, and the model wins 40% of rounds. This sample is too small for a reliable conclusion, but it does **not** corroborate the proxy result. The strategy cannot be promoted to production on current evidence.

## Post-selection forecast calibration

A separate rolling calibration fits `actual proxy score = intercept + slope × expected lineup score` using only earlier rounds; it begins after 20 prior rounds and never changes the selected lineup.

| Strategy | Raw score MAE | Calibrated score MAE | Raw score RMSE | Calibrated score RMSE | Raw bias | Calibrated bias |
|---|---:|---:|---:|---:|---:|---:|
| Model | 43.83 | 43.37 | 57.71 | 57.08 | +7.25 | +6.80 |
| Previous-five baseline | 111.64 | 52.66 | 127.83 | 63.58 | +110.52 | +3.65 |

This shows the previous-five baseline's expected lineup score is severely overoptimistic after optimization. Post-selection calibration corrects the forecast score, but it does not fix the baseline's lineup choices.

## Decision

Keep V7 as an experimental challenger only. The proxy suggests zero-inclusive training and past-only calibration are promising, but missing rows, historical availability, market prices, coach prices and transfer malus remain unresolved. The strict sample of five shared rounds is insufficient and does not show model superiority. Do not change the production optimizer or model based on this experiment alone.

## Additional artifacts

- Paired proxy bootstrap: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_proxy_bootstrap.md`
- V6 vs V7 paired bootstrap: `reports/audit/dunkest_v6_v7_lineup_strategy_paired_bootstrap_20261014_v1.md`
- Past-only post-selection calibration: `reports/audit/dunkest_lineup_postselection_calibration_20261014_v1.md`
