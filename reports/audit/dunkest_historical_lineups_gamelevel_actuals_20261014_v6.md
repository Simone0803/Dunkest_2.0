# Dunkest historical lineup experiment with game-level official actuals — V5

Generated (UTC): 2026-10-14T13:08:00.321940+00:00

V5 fixes the V3 candidate-slate bug: target teams/opponents are rebuilt from the full NBA schedule for the target season/date, not inferred from sparse teams in the Dunkest outcome table. Candidate team assignment uses the latest strictly pre-target linked NBA team where available. Training remains past-only.

## Method

For each historical target round, training predictors are built from the player's latest archived row strictly before that target round; target-round PDK is joined only as the label. Target matchup and opponent-defence features come from the target schedule and historical defensive stats. Realized player score is taken directly from the official Dunkest player-week-round archive, avoiding the incomplete single-date game-level join. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-observation mean baseline.

## Game-level reconstruction validation

- Historical weekly rows compared: 93,734
- Rows matching weekly PDK within 0.02 points: 93,728 (99.994%)
- Mean absolute difference: 0.00149 PDK

The optimizer uses the repository roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model. The historical candidate pool, prices and availability remain proxies; missing player scores remain unknown and exclude a round from strict paired comparisons.

## Strict observed-only results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24                 3                      241.941667                          215.25000                        26.691667                            26.2300                         1.0               243.000                            0.796151                     0.943451
       19         2024-25                 1                      212.710000                          195.68500                        17.025000                            17.0250                         1.0               229.000                            0.908297                     0.924444
        9         2022-23                 4                      196.728750                          159.59125                        37.137500                            39.3875                         1.0               175.250                            0.751111                     0.986486
   POOLED 2022-23–2024-25                 8                      215.681250                          184.97500                        30.706250                            21.6275                         1.0               207.375                            0.787649                     0.962593

## Explicit proxy scenario: missing player PDK set to zero

This sensitivity scenario assumes a candidate absent from the historical Dunkest player-week-round outcome archive scores 0. It is an explicit proxy for an unobserved outcome, not a certified actual. Interpret its strategy comparison as exploratory only.

season_id          season  rounds_evaluated_proxy  mean_model_realized_team_score_proxy  mean_baseline_realized_team_score_proxy  mean_delta_model_minus_baseline_proxy  median_delta_model_minus_baseline_proxy  model_win_rate_vs_baseline_proxy  mean_candidate_count
       13         2023-24                     147                            140.506701                               121.536054                              18.970646                                  12.4100                          0.619048            245.965986
       19         2024-25                     152                            144.236612                               125.270921                              18.965691                                  15.4875                          0.625000            245.085526
        9         2022-23                     159                            124.229686                               115.355440                               8.874245                                   9.7150                          0.566038            226.364780
   POOLED 2022-23–2024-25                     458                            136.093821                               120.629902                              15.463919                                  12.5450                          0.602620            238.868996

## Paired uncertainty

- Strict observed-only estimates use only rounds with complete observed player and coach outcomes; proxy estimates are reported separately and must not be interpreted as certified results.

## Selection-conditioned calibration

- Model: mean expected team score 209.53, realized 217.51 (optimism gap -7.978)
- Raw previous-five baseline strict: expected 286.47, realized 190.54 (gap 95.925)
- Model proxy: expected 209.37, realized 136.09 (gap 73.278)
- Baseline proxy: expected 275.39, realized 120.63 (gap 154.756)
The proxy comparison favors the model against this raw baseline, but the zero-for-missing assumption and uncalibrated baseline prevent a production-superiority claim.

## Coverage

- Round outcomes: {'selected_actuals_incomplete': 450, 'evaluated': 8, 'candidate_pool_too_small': 3, 'optimization_failed': 3}
- Optimized lineup records: 916

## Critical caveats

The candidate universe is reconstructed from prior-season-round observations and the latest linked NBA team available before each target round. Players never observed earlier in the season, late additions, and traded players without a prior linked appearance for the new team may be missing or misassigned. CR and role are lagged proxies, not certified pre-lock market state.

Historical availability is not timestamped; p_play=1 is an eligibility proxy, not verified availability. A selected lineup is included in paired realized-score metrics only when all selected player scores and the coach base score are observed. Missing scores are not imputed to zero.

Coach prices are missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is zero because historical carried rosters are not archived. This compares fresh independent round lineups, not a sequential roster with transfers. The full slate comes from NBA team-game logs, but this remains a reconstructed proxy rather than a certified historical Dunkest market backtest.

Production model/configuration remains unchanged.

## Artifacts

- Strict observed-only metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v6_metrics.csv`
- Explicit proxy metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v6_proxy_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v6_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v6_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v6.json`
