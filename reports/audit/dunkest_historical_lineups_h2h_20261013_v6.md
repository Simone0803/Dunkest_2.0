# Dunkest historical lineup experiment with H2H features — V6

Generated (UTC): 2026-10-13T09:43:30.056917+00:00

V6 compares three optimizer strategies on the same restricted pre-target candidate pool: a model without H2H, a model with shrunk player-vs-opponent history, and the previous-five-round PDK baseline.

## Method

For target round r, the candidate pool carries forward each player's most recent archived row strictly before r. CR, role and player form are therefore lagged; if a player did not appear in r−1, their last observed price is carried forward. The current round's player score is used only as the realized outcome. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  mean_h2h_minus_model  median_h2h_minus_model  h2h_win_rate_vs_model  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24               132                      163.161212                         142.537159                        20.624053             -7.371780                 -2.2675               0.454545                            15.9825                    0.628788            214.280303                            0.601529                     0.950261
       19         2024-25               138                      167.889710                         143.878696                        24.011014             -4.254964                 -0.0225               0.485507                            20.8900                    0.659420            213.057971                            0.601715                     0.951834
        9         2022-23               139                      152.066259                         134.732050                        17.334209             -5.423525                 -4.8000               0.417266                            17.9250                    0.633094            201.964029                            0.612537                     0.945910
   POOLED 2022-23–2024-25               409                      160.985990                         140.337213                        20.648778             -5.658020                 -2.1250               0.452323                            17.6550                    0.640587            209.682152                            0.605333                     0.949313

## Coverage

- Round outcomes: {'evaluated': 409, 'optimization_failed': 49, 'candidate_pool_too_small': 6}
- Optimized lineup records: 1,227

## H2H conclusion

Across 409 evaluated rounds, the H2H model selected lineups averaging 155.33 realized points including neutral-credit coach base score, versus 160.99 for the same model without H2H (delta -5.66; H2H won 45.2% of rounds). The stratified paired-bootstrap 95% interval for H2H minus no-H2H is [-9.49, -1.77]. The H2H challenger is therefore rejected for lineup use in its current form, despite the small improvement in the separate game-level holdout. See `dunkest_historical_lineups_h2h_20261013_v6_paired_bootstrap.md` for paired results.

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players with no earlier observed row in the season are not candidates. The result cannot be called a complete historical market optimum.

Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.

The 2025/26 game-level H2H holdout motivates this experiment but does not tune this test. Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_h2h_20261013_v6_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_h2h_20261013_v6_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_h2h_20261013_v6_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_h2h_20261013_v6.json`
