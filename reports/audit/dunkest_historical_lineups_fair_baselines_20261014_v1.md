# Historical lineup comparison: MILP model vs same-constraint baselines — V6

Generated (UTC): 2026-10-14T19:15:54.640143+00:00

## Method

Across every high-confidence mapped historical target round, all four strategies used the same lagged candidate universe, 95 CR total budget, 4G/4F/2C roster composition, five starters, sixth man, four bench slots, captain rule, team cap including coach, coach candidate set, and CBC settings. Only the player selection score changed: walk-forward model, previous-five mean, PDK-per-CR, or within-role ranking. Missing realized outcomes were not imputed as zero.

## Strict observed-only results

    season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_previous5_baseline_realized_team_score  mean_pdk_per_cr_baseline_realized_team_score  mean_role_rank_baseline_realized_team_score  mean_delta_model_minus_previous5  median_delta_model_minus_previous5  model_win_rate_vs_previous5  mean_delta_model_minus_pdk_per_cr  model_win_rate_vs_pdk_per_cr  mean_delta_model_minus_role_rank  model_win_rate_vs_role_rank  mean_candidate_count  mean_candidate_target_row_coverage
            9         2022-23                 1                        216.5300                                     201.4800                                       129.150                                     222.6600                            15.050                              15.050                          1.0                            87.3800                           1.0                             -6.13                          0.0                 233.0                            0.836910
           19         2024-25                 1                        194.6650                                     195.1450                                       134.740                                     171.8950                            -0.480                              -0.480                          0.0                            59.9250                           1.0                             22.77                          1.0                 230.0                            0.852174
POOLED_STRICT 2022-23–2024-25                 2                        205.5975                                     198.3125                                       131.945                                     197.2775                             7.285                               7.285                          0.5                            73.6525                           1.0                              8.32                          0.5                 231.5                            0.844542

## Coverage

- Rounds where all four strategies optimized successfully: 409
- Rounds with complete observed actuals for all four strategies: 2
- Rounds excluded from paired score comparisons due to missing outcomes: 407

## Limitations

- This is not a certified full-market backtest: the candidate pool carries forward only players observed in historical season archives; late additions and absent players can be missing.
- Historical coach CR and exact price-adjusted coach points are unavailable; coaches use 10 CR and reconstructed neutral-credit base scores.
- This compares four selection policies under the same MILP constraints; it does not certify that the historical candidate universe matches the full pre-lock Dunkest market.
- With only two fully observed paired rounds, differences and bootstrap intervals cannot support a strategy winner.

Production model/configuration unchanged.
