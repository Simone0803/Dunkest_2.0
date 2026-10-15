# Rest/schedule features — paired cluster bootstrap

Generated UTC: 2026-10-13T09:57:02.908263+00:00

Paired sample: 55,565 player-round rows, 467 season-week-round clusters.

## Metrics

                        scope  n_player_rounds  n_rounds  mae_base  mae_rest  delta_mae_rest_minus_base  rmse_base  rmse_rest  round_win_rate_rest_better
                           13            18279       150  7.522331  7.494350                  -0.027982   9.830148   9.790930                    0.633333
                           19            18882       155  7.502886  7.482163                  -0.020723   9.820832   9.776668                    0.561290
                            9            18404       162  7.483174  7.456478                  -0.026696   9.738037   9.694956                    0.549383
pooled_macro_season_bootstrap            55565       467  7.502797  7.477663                  -0.025134   9.796339   9.754185                    0.581335

## Paired bootstrap (10,000 replicates)

- Macro-season delta MAE (rest minus baseline), 95% CI: [-0.0339, -0.0168].
- Bootstrap fraction with delta below zero: 1.0000.
- Per-season intervals:
  - 13: [-0.0417, -0.0154], fraction below zero 1.0000.
  - 19: [-0.0339, -0.0060], fraction below zero 0.9963.
  - 9: [-0.0450, -0.0103], fraction below zero 0.9998.

## Decision

Do not promote features based on tiny or unstable player-level gains. Any candidate must subsequently improve a complete, leakage-safe lineup backtest; this experiment does not change production.
