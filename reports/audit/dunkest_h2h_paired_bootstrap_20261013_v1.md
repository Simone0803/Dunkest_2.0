# Player-vs-opponent features — paired cluster bootstrap

Generated UTC: 2026-10-13T09:26:07.518450+00:00
Paired targets: 55,565; round clusters: 467.

## Metrics

      season                          comparison     n  rounds    mae_a    mae_b  delta_mae   rmse_a   rmse_b  round_win_rate_a_better
          13 h2h_unshrunk_minus_expanded_matchup 18279     150 7.469156 7.522331  -0.053175 9.741477 9.830148                 0.546667
          19 h2h_unshrunk_minus_expanded_matchup 18882     155 7.443108 7.502886  -0.059778 9.730862 9.820832                 0.606452
           9 h2h_unshrunk_minus_expanded_matchup 18404     162 7.450335 7.483174  -0.032839 9.658124 9.738037                 0.500000
macro_season h2h_unshrunk_minus_expanded_matchup 55565     467 7.454200 7.502797  -0.048597 9.710154 9.796339                 0.551039
          13   h2h_shrunk_minus_expanded_matchup 18279     150 7.469819 7.522331  -0.052513 9.739426 9.830148                 0.520000
          19   h2h_shrunk_minus_expanded_matchup 18882     155 7.441030 7.502886  -0.061856 9.722286 9.820832                 0.600000
           9   h2h_shrunk_minus_expanded_matchup 18404     162 7.452629 7.483174  -0.030545 9.660289 9.738037                 0.475309
macro_season   h2h_shrunk_minus_expanded_matchup 55565     467 7.454492 7.502797  -0.048305 9.707334 9.796339                 0.531770
          13       h2h_shrunk_minus_h2h_unshrunk 18279     150 7.469819 7.469156   0.000662 9.739426 9.741477                 0.480000
          19       h2h_shrunk_minus_h2h_unshrunk 18882     155 7.441030 7.443108  -0.002078 9.722286 9.730862                 0.541935
           9       h2h_shrunk_minus_h2h_unshrunk 18404     162 7.452629 7.450335   0.002293 9.660289 9.658124                 0.537037
macro_season       h2h_shrunk_minus_h2h_unshrunk 55565     467 7.454492 7.454200   0.000293 9.707334 9.710154                 0.519658

## Bootstrap (10,000 replicates)

### h2h_unshrunk_minus_expanded_matchup
- Macro-season delta MAE 95% CI: [-0.0824, -0.0220] (negative favors the first model).
- Fraction below zero: 1.0000.
- Season 13: CI [-0.1245, -0.0094], fraction below zero 0.9994.
- Season 19: CI [-0.1131, -0.0237], fraction below zero 1.0000.
- Season 9: CI [-0.0957, 0.0061], fraction below zero 0.9195.
### h2h_shrunk_minus_expanded_matchup
- Macro-season delta MAE 95% CI: [-0.0803, -0.0221] (negative favors the first model).
- Fraction below zero: 1.0000.
- Season 13: CI [-0.1208, -0.0104], fraction below zero 0.9998.
- Season 19: CI [-0.1159, -0.0246], fraction below zero 1.0000.
- Season 9: CI [-0.0846, 0.0054], fraction below zero 0.9260.
### h2h_shrunk_minus_h2h_unshrunk
- Macro-season delta MAE 95% CI: [-0.0050, 0.0057] (negative favors the first model).
- Fraction below zero: 0.4570.
- Season 13: CI [-0.0081, 0.0096], fraction below zero 0.4333.
- Season 19: CI [-0.0104, 0.0061], fraction below zero 0.6909.
- Season 9: CI [-0.0079, 0.0129], fraction below zero 0.3470.

## Interpretation

Historical head-to-head features are exploratory and depend on reconstructed player/opponent identity. The shrinkage feature uses three pseudo-observations from the player previous-five-round PDK mean. No production code or configuration was changed. A statistically detectable but tiny gain is not sufficient to promote a feature.
