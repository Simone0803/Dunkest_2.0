# Expanded matchup features — paired cluster bootstrap

Generated UTC: 2026-10-13T09:16:24.226019+00:00

Paired sample: 55,565 player-round rows, 467 season-week-round clusters.

## Metrics

                        scope                    comparison  n_player_rounds  n_rounds    mae_a    mae_b  delta_mae_a_minus_b   rmse_a   rmse_b  round_win_rate_a_better
                           13  expanded_v2_minus_matchup_v1            18279       150 7.522331 7.533677            -0.011345 9.830148 9.850588                 0.506667
                           13 expanded_v2_minus_credit_only            18279       150 7.522331 7.535738            -0.013406 9.830148 9.868543                 0.506667
                           19  expanded_v2_minus_matchup_v1            18882       155 7.502886 7.513295            -0.010409 9.820832 9.836828                 0.561290
                           19 expanded_v2_minus_credit_only            18882       155 7.502886 7.533667            -0.030781 9.820832 9.860828                 0.619355
                            9  expanded_v2_minus_matchup_v1            18404       162 7.483174 7.489628            -0.006454 9.738037 9.740679                 0.518519
                            9 expanded_v2_minus_credit_only            18404       162 7.483174 7.493187            -0.010014 9.738037 9.741778                 0.586420
pooled_macro_season_bootstrap  expanded_v2_minus_matchup_v1            55565       467 7.502797 7.512200            -0.009403 9.796339 9.809365                 0.528908
pooled_macro_season_bootstrap expanded_v2_minus_credit_only            55565       467 7.502797 7.520864            -0.018067 9.796339 9.823717                 0.571734

## Paired bootstrap (10,000 replicates)

### expanded_v2_minus_matchup_v1
- Macro-season delta MAE 95% CI: [-0.0157, -0.0033] (negative favors expanded matchup).
- Fraction of bootstrap estimates below zero: 0.9990.
- Per-season intervals:
  - 13: [-0.0224, -0.0002], fraction below zero 0.9761.
  - 19: [-0.0203, -0.0010], fraction below zero 0.9848.
  - 9: [-0.0184, 0.0057], fraction below zero 0.8464.
### expanded_v2_minus_credit_only
- Macro-season delta MAE 95% CI: [-0.0316, -0.0043] (negative favors expanded matchup).
- Fraction of bootstrap estimates below zero: 0.9944.
- Per-season intervals:
  - 13: [-0.0353, 0.0097], fraction below zero 0.8769.
  - 19: [-0.0515, -0.0081], fraction below zero 0.9954.
  - 9: [-0.0361, 0.0169], fraction below zero 0.7723.

## Decision

Expanded matchup adds defensive STL/BLK/TOV, possession/pace proxies, and 5-game recent trends. Treat any tiny gain as exploratory: do not change production unless the effect is both statistically stable and practically meaningful. Historical matchup date mapping and lagged-credit caveats remain unchanged.
