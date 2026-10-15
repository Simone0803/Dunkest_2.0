# Dunkest historical lineup experiment with game-level official actuals — V3

Generated (UTC): 2026-10-14T12:04:22.799099+00:00

V3 fixes two issues in earlier experiments: it uses a high-confidence round-date slate for official player actuals and trains on strictly pre-target player observations. V2 was superseded because its training matrix included same-round labels in predictor columns.

## Method

For each historical target round, training predictors are built from the player's latest archived row strictly before that target round; target-round PDK is joined only as the label. Target matchup and opponent-defence features come from the target schedule and historical defensive stats. The round date is accepted only if at least 75% of unique player-date links agree and at least 10 unique player links exist. Realized player PDK is summed from official game-level rows on that season/date where gameValidForDunkest=True. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-observation mean baseline.

## Game-level reconstruction validation

- Historical weekly rows compared: 93,734
- Rows matching weekly PDK within 0.02 points: 93,728 (99.994%)
- Mean absolute difference: 0.00149 PDK

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24               132                      162.996364                         142.537159                        20.459205                            16.1625                    0.643939            214.280303                            0.601529                     0.950261
       19         2024-25               138                      169.466775                         143.878696                        25.588080                            23.4225                    0.688406            213.057971                            0.601715                     0.951834
        9         2022-23               139                      150.188129                         134.732050                        15.456079                            12.2350                    0.589928            201.964029                            0.612537                     0.945910
   POOLED 2022-23–2024-25               409                      160.826614                         140.337213                        20.489401                            16.8200                    0.640587            209.682152                            0.605333                     0.949313

## Paired uncertainty

- Mean model minus baseline: **+20.49 PDK**
- Model wins on **64.1%** of paired rounds
- Season-stratified paired-round bootstrap 95% CI: **[+15.19, +25.78] PDK**
- All 50,000 bootstrap replicates had a positive pooled mean difference

## Selection-conditioned calibration

- Model: mean expected team score **207.82**, realized **160.83** (optimism gap **46.997**)
- Raw previous-five-observation baseline: mean expected **271.72**, realized **140.34** (optimism gap **131.383**)

The raw baseline is severely overoptimistic after lineup selection. The positive paired comparison is meaningful evidence against this naïve baseline, but it is not enough to declare strategy superiority over a properly calibrated alternative. Calibrate the baseline and post-selection score distribution before any production promotion.

## Coverage

- Round outcomes: {'evaluated': 409, 'optimization_failed': 49, 'candidate_pool_too_small': 6}
- Optimized lineup records: 818

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so late additions and players with no earlier observed row in the season are not candidates. The candidate pool contains about 210 players on average and covers about 94.9% of players appearing in the target-round outcome archive; candidate_target_row_coverage (~60.5%) is the share of candidates with a weekly aggregate row, not the share with reconstructed actuals.

Coach prices are missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. This compares fresh independent round lineups, not a sequential roster with transfers, and historical rule differences may remain. Forty-nine rounds failed optimization and six had candidate pools too small; metrics cover the 409 rounds where both strategies were successfully evaluated.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v3_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v3_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v3_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v3.json`
