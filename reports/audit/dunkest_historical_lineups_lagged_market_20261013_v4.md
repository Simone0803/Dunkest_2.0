# Dunkest historical lineup experiment with lagged market — V1

Generated (UTC): 2026-10-13T08:27:54.391131+00:00

**Sampling note:** this V4 run evaluates every third high-confidence round in each held-out season to keep the MILP comparison tractable. It is a diagnostic sample, not an exhaustive full-season result.

## Method

For target round r, the candidate pool carries forward each player's most recent archived row strictly before r. CR, role and player form are therefore lagged; if a player did not appear in r−1, their last observed price is carried forward. The current round's player score is used only as the realized outcome. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24                44                      171.529318                         155.186705                        16.342614                             16.010                    0.636364            205.818182                            0.605521                     0.946971
       19         2024-25                45                      173.901778                         145.050222                        28.851556                             22.115                    0.711111            221.822222                            0.602905                     0.958064
        9         2022-23                46                      157.618696                         120.176522                        37.442174                             40.465                    0.760870            212.586957                            0.602385                     0.948143
   POOLED 2022-23–2024-25               135                      167.580222                         139.878481                        27.701741                             28.125                    0.703704            213.459259                            0.603581                     0.951068

## Coverage

- Round outcomes: {'evaluated': 135, 'optimization_failed': 18}
- Optimized lineup records: 270

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players with no earlier observed row in the season are not candidates. The result cannot be called a complete historical market optimum.

Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v4_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v4_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v4_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v4.json`
