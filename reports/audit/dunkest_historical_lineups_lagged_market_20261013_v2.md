# Dunkest historical lineup experiment with lagged market — V1

Generated (UTC): 2026-10-13T08:23:38.021754+00:00

## Method

For target round r, the candidate pool is taken from archived player rows in round r−1. CR, role and player form are therefore lagged; the current round's player score is used only as the realized outcome. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24                30                       91.444667                          99.664500                        -8.219833                                0.0                    0.200000             56.266667                            0.410714                     0.166073
       19         2024-25                36                      104.499861                         101.730000                         2.769861                                0.0                    0.333333             59.361111                            0.429466                     0.189392
        9         2022-23                38                       73.239737                          73.638421                        -0.398684                                0.0                    0.263158             51.000000                            0.352770                     0.147618
   POOLED 2022-23–2024-25               104                       89.311971                          90.869952                        -1.557981                                0.0                    0.269231             55.413462                            0.396033                     0.167402

## Coverage

- Round outcomes: {'candidate_pool_too_small': 124, 'no_candidates': 123, 'optimization_failed': 113, 'evaluated': 104}
- Optimized lineup records: 208

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players absent from the prior archived round are not candidates. The result cannot be called a complete historical market optimum.

Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v2_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v2_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v2_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v2.json`
