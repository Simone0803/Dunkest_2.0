# Dunkest historical lineup comparison — matchup V2 vs rest/schedule V6

Generated (UTC): 2026-10-13T10:03:43.521537+00:00

This is a paired historical lineup proxy comparing expanded-matchup V2 against V6 with past-only rest/schedule features on the same candidate pool and rounds, subject to candidate availability and the 1-second MILP solve limit.

## Method

For target round r, the candidate pool carries forward each player's most recent archived row strictly before r. CR, role and player form are therefore lagged; if a player did not appear in r−1, their last observed price is carried forward. The current round's player score is used only as the realized outcome. Two walk-forward player models are trained on identical earlier seasons: expanded-matchup V2 and V6 with seven additional past-only rest/schedule features.

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model. The only model difference is the seven past-only rest/schedule inputs.

## Results

season_id          season  rounds_evaluated  mean_v2_realized_team_score  mean_v6_realized_team_score  mean_delta_v6_minus_v2  median_delta_v6_minus_v2  v6_win_rate_vs_v2  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24               132                   163.115947                   164.843182                1.727235                      0.00           0.492424            214.280303                            0.601529                     0.950261
       19         2024-25               138                   166.380000                   169.748261                3.368261                      0.32           0.514493            213.057971                            0.601715                     0.951834
        9         2022-23               139                   150.330755                   149.928237               -0.402518                      0.00           0.467626            201.964029                            0.612537                     0.945910
   POOLED 2022-23–2024-25               409                   159.872176                   161.429303                1.557127                      0.00           0.491443            209.682152                            0.605333                     0.949313

## Rest/schedule coverage

- {'policy': 'For each target team and opponent, only team-game dates strictly earlier than target_date are used. All games on target_date are excluded because archives are date-only.', 'features': ['team_days_since_game_v6', 'opponent_days_since_game_v6', 'team_games_prior7d_v6', 'opponent_games_prior7d_v6', 'team_back_to_back_v6', 'opponent_back_to_back_v6', 'rest_advantage_days_v6'], 'rows_with_team_prior_game': 93652, 'rows_with_opponent_prior_game': 90219, 'rows_with_complete_rest_features': 90219, 'target_date_same_day_games_excluded': True}

## Coverage

- Round outcomes: {'evaluated': 409, 'optimization_failed': 49, 'candidate_pool_too_small': 6}
- Optimized lineup records: 818

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players with no earlier observed row in the season are not candidates. The result cannot be called a complete historical market optimum.

Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1.json`
