# Dunkest historical lineup experiment with game-level official actuals — V2

> **SUPERSEDED — do not use the lineup-performance metrics.** V2 training used same-round target information in predictor columns. The actual-score reconstruction validation remains useful; use the V3 leakage-safe lineup experiment for performance estimates. See `dunkest_historical_lineups_gamelevel_actuals_20261014_v2_superseded.md`.

Generated (UTC): 2026-10-14T11:54:35.159479+00:00

This version corrects the earlier game-ID-union method, which could include a repeated box-score signature from another date. Realized player scores are reconstructed from the official Dunkest-valid slate on a high-confidence round date.

## Method

For target round r, each candidate's latest archived row strictly before r supplies lagged CR, role, team and form. A round date is accepted only if at least 75% of unique player-date links agree and at least 10 unique player links exist. Realized player PDK is the sum of official game-level PDK for that season/date where gameValidForDunkest=True; candidate identities absent from the official season archive are excluded. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.

## Game-level reconstruction validation

- Historical weekly rows compared: 93,734
- Rows matching weekly PDK within 0.02 points: 93,728 (99.994%)
- Mean absolute difference: 0.00149 PDK

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24               132                      163.161212                         142.537159                        20.624053                            15.9825                    0.628788            214.280303                            0.601529                     0.950261
       19         2024-25               138                      167.889710                         143.878696                        24.011014                            20.8900                    0.659420            213.057971                            0.601715                     0.951834
        9         2022-23               139                      151.740827                         134.732050                        17.008777                            17.9250                    0.625899            201.964029                            0.612537                     0.945910
   POOLED 2022-23–2024-25               409                      160.875391                         140.337213                        20.538178                            17.6550                    0.638142            209.682152                            0.605333                     0.949313

## Paired uncertainty

- Mean model minus baseline: **+20.54 PDK**
- Model wins on **63.8%** of paired rounds
- Season-stratified paired-round bootstrap 95% CI: **[+15.06, +25.90] PDK**
- All 50,000 bootstrap replicates had a positive pooled mean difference

See `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v2_bootstrap.md` for the reproducible uncertainty audit.

## Coverage

- Round outcomes: {'evaluated': 409, 'optimization_failed': 49, 'candidate_pool_too_small': 6}
- Optimized lineup records: 818

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so late additions and players with no earlier observed row in the season are not candidates. The candidate pool contains about 210 players on average and covers about 94.9% of players appearing in the target-round outcome archive; candidate_target_row_coverage (~60.5%) is the share of candidates with a weekly aggregate row, not the share with reconstructed actuals.

Coach prices are missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. This compares fresh independent round lineups, not a sequential roster with transfers, and historical rule differences may remain. Forty-nine rounds failed optimization and six had candidate pools too small; metrics cover the 409 rounds where both strategies were successfully evaluated.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v2_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v2_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v2_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v2.json`
