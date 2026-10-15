# Dunkest historical lineup experiment with game-level official actuals — V1

Generated (UTC): 2026-10-14T11:46:34.798675+00:00

This run repeats the restricted-universe walk-forward lineup comparison but reconstructs realized player scores from official Dunkest per-game PDK rows over the mapped fixture set, instead of treating missing weekly aggregate rows as zero by default.

## Method

For target round r, each candidate's latest archived row strictly before r supplies lagged CR, role, team and form. The round's fixture IDs are recovered from the persisted game-link dataset. Realized player PDK is the sum of official game-level PDK only where gameValidForDunkest=True; candidate identities absent from the official season archive are excluded. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.

## Game-level reconstruction validation

- Historical weekly rows compared: 93,753
- Rows matching weekly PDK within 0.02 points: 93,706 (99.950%)
- Mean absolute difference: 0.01027 PDK

The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24               132                      163.172576                         142.537159                        20.635417                            15.9825                    0.628788            214.280303                            0.601529                     0.950261
       19         2024-25               138                      167.889710                         144.563587                        23.326123                            20.3450                    0.659420            213.057971                            0.601715                     0.951834
        9         2022-23               139                      151.740827                         134.732050                        17.008777                            17.9250                    0.625899            201.964029                            0.612537                     0.945910
   POOLED 2022-23–2024-25               409                      160.879059                         140.568301                        20.310758                            17.6550                    0.638142            209.682152                            0.605333                     0.949313

## Paired uncertainty

- Mean model minus baseline: **+20.31 PDK**
- Model wins on **63.8%** of paired rounds
- Season-stratified paired-round bootstrap 95% CI: **[+14.79, +25.72] PDK**
- All 50,000 bootstrap replicates had a positive pooled mean difference

See `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v1_bootstrap.md` for the reproducible uncertainty audit.

## Coverage

- Round outcomes: {'evaluated': 409, 'optimization_failed': 49, 'candidate_pool_too_small': 6}
- Optimized lineup records: 818

## Critical caveats

This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players with no earlier observed row in the season are not candidates. The result cannot be called a complete historical market optimum.

Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v1_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v1_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v1_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v1.json`
