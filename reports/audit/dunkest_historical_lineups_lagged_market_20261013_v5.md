# Dunkest historical lineup experiment with lagged market — V1

Generated (UTC): 2026-10-13T08:32:09.972892+00:00

This is the exhaustive V5 run over all high-confidence mapped target rounds in the three held-out seasons, subject to candidate availability and the 1-second MILP solve limit.

## Method

For target round r, the candidate pool carries forward each player's most recent archived row strictly before r. CR, role and player form are therefore lagged; if a player did not appear in r−1, their last observed price is carried forward. The current round's player score is used only as the realized outcome. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24               132                      163.161212                         142.537159                        20.624053                            15.9825                    0.628788            214.280303                            0.601529                     0.950261
       19         2024-25               138                      167.889710                         143.878696                        24.011014                            20.8900                    0.659420            213.057971                            0.601715                     0.951834
        9         2022-23               139                      151.740827                         134.732050                        17.008777                            17.9250                    0.625899            201.964029                            0.612537                     0.945910
   POOLED 2022-23–2024-25               409                      160.875391                         140.337213                        20.538178                            17.6550                    0.638142            209.682152                            0.605333                     0.949313

## Coverage

- Round outcomes: {'evaluated': 409, 'optimization_failed': 49, 'candidate_pool_too_small': 6}
- Optimized lineup records: 818

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players with no earlier observed row in the season are not candidates. The result cannot be called a complete historical market optimum.

Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v5_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v5_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v5_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v5.json`
