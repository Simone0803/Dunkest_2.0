# Dunkest historical lineup experiment with calibrated zero-inclusive lineups — V8

Generated (UTC): 2026-10-14T13:28:55.550406+00:00

V8 fixes the V3 candidate-slate bug: target teams/opponents are rebuilt from the full NBA schedule for the target season/date, not inferred from sparse teams in the Dunkest outcome table. Candidate team assignment uses the latest strictly pre-target linked NBA team where available. Training remains past-only.

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

## Expanded official-record scoring sensitivity

Missing player scores remain unknown unless the official game-level endpoint has an explicit non-valid player-game row; only then is 0 used in this separate sensitivity. This can recover more complete scores but does not certify that the player was eligible in the historical pre-lock market.

season_id          season  rounds_evaluated_expanded  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline
       13         2023-24                          5                      164.314000                         137.726000                        26.588000                             21.180                    1.000000
       19         2024-25                          1                      236.875000                         126.855000                       110.020000                            110.020                    1.000000
        9         2022-23                          7                      173.210714                         195.782143                       -22.571429                            -20.415                    0.142857
   POOLED 2022-23–2024-25                         13                      174.686154                         168.150769                         6.535385                              3.150                    0.538462

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
       19         2024-25                     152                            167.588224                               122.418849                              45.169375                                  44.5425                          0.776316            245.085526
        9         2022-23                     159                            148.619119                               112.971226                              35.647893                                  27.0000                          0.685535            226.364780
   POOLED 2022-23–2024-25                     458                            162.384170                               118.506026                              43.878144                                  41.9250                          0.755459            238.868996

## Paired uncertainty

- Strict observed-only estimates use only rounds with complete observed player and coach outcomes; proxy estimates are reported separately and must not be interpreted as certified results.

## Selection-conditioned calibration

- Model: mean expected team score 172.72, realized 195.79 (optimism gap -23.072)
- Raw previous-five baseline strict: expected 254.57, realized 197.60 (gap 56.970)
- Model proxy: expected 169.59, realized 162.38 (gap 7.205)
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

- Strict observed-only metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_metrics.csv`
- Explicit zero-for-missing proxy metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_proxy_metrics.csv`
- Expanded explicit-nonvalid-zero metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_expanded_metrics.csv`
- Player forecasts: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_player_forecasts.csv`
- Expanded paired bootstrap: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_expanded_bootstrap.md`
- Missing outcome recovery audit: `reports/audit/dunkest_missing_player_round_outcomes_20261014_v1.md`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8.json`
