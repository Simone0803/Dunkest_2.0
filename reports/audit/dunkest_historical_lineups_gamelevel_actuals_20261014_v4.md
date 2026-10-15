# Dunkest historical lineup experiment with game-level official actuals — V4

> **Superseded by V5.** V4 fixed slate coverage but only 8 rounds had complete observed player actuals. Its original paired-uncertainty lines were copied from V3 and were not valid for V4; they are corrected below.

Generated (UTC): 2026-10-14T12:37:00.129062+00:00

V4 fixes the V3 candidate-slate bug: target teams/opponents are rebuilt from the full NBA schedule for the target season/date, not inferred from sparse teams in the Dunkest outcome table. Candidate team assignment uses the latest strictly pre-target linked NBA team where available. Training remains past-only.

## Method

For each historical target round, training predictors are built from the player's latest archived row strictly before that target round; target-round PDK is joined only as the label. Target matchup and opponent-defence features come from the target schedule and historical defensive stats. The round date is accepted only if at least 75% of unique player-date links agree and at least 10 unique player links exist. Realized player PDK is summed from official game-level rows on that season/date where gameValidForDunkest=True. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-observation mean baseline.

## Game-level reconstruction validation

- Historical weekly rows compared: 93,734
- Rows matching weekly PDK within 0.02 points: 93,728 (99.994%)
- Mean absolute difference: 0.00149 PDK

The optimizer uses the repository roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model. The historical candidate pool, prices and availability remain proxies; missing realized player scores are left missing and exclude a round from paired score comparisons.

## Results

season_id          season  rounds_evaluated  mean_model_realized_team_score  mean_baseline_realized_team_score  mean_delta_model_minus_baseline  median_delta_model_minus_baseline  model_win_rate_vs_baseline  mean_candidate_count  mean_candidate_target_row_coverage  mean_target_players_covered
       13         2023-24                 3                      241.941667                          215.25000                        26.691667                            26.2300                         1.0               243.000                            0.796151                     0.943451
       19         2024-25                 1                      212.710000                          195.68500                        17.025000                            17.0250                         1.0               229.000                            0.908297                     0.924444
        9         2022-23                 4                      196.728750                          159.59125                        37.137500                            39.3875                         1.0               175.250                            0.751111                     0.986486
   POOLED 2022-23–2024-25                 8                      215.681250                          184.97500                        30.706250                            21.6275                         1.0               207.375                            0.787649                     0.962593

## Paired uncertainty

No V4 paired bootstrap was computed. The previous numeric claims were inherited from V3 and do not describe this V4 sample. Only 8 rounds have complete observed player outcomes for both selected lineups; this sample is too small for a useful superiority claim.

## Selection-conditioned calibration

- Model: mean expected team score 209.37, realized 217.51 (optimism gap -8.140)
- Raw previous-five-observation baseline: mean expected 275.39, realized 190.54 (optimism gap 84.843)
The raw baseline is severely overoptimistic after lineup selection. The positive paired comparison is conditional evidence against this naïve baseline, not proof of superiority over a properly calibrated alternative.

## Coverage

- Round outcomes: {'selected_actuals_incomplete': 450, 'evaluated': 8, 'candidate_pool_too_small': 3, 'optimization_failed': 3}
- Optimized lineup records: 916

## Critical caveats

The candidate universe is reconstructed from prior-season-round observations and the latest linked NBA team available before each target round. Players never observed earlier in the season, late additions, and traded players without a prior linked appearance for the new team may be missing or misassigned. CR and role are lagged proxies, not certified pre-lock market state.

Historical availability is not timestamped. The strict realized-score metric excludes a round if any selected player lacks an observed valid PDK score; consequently, 450 rounds have incomplete realized outcomes and only 8 enter the strict paired metric. Coach prices are missing; all coaches use 10 CR, and transfer malus is zero because carried rosters are not archived. V4 found feasible lineups for most rounds, but it does not certify full historical Dunkest strategy performance.

Production model/configuration remains unchanged.

## Artifacts

- Round metrics: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v4_metrics.csv`
- Per-round outcomes: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v4_rounds.csv`
- Selected lineups: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v4_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v4.json`
