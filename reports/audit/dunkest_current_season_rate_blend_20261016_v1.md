# Current-season per-minute rate blending — V1

## Protocol

- Source: `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet` joined to `data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet` on existing NBA game/player identifiers.
- Outcome rows with missing/non-positive actual minutes were excluded; 93,454 matched positive-minute player-game rows remained.
- Development evaluation covers target seasons 2022/23, 2023/24 and 2024/25 (49,455 player-game rows where both prior-season and current-season pre-target rates were available). The 2025/26 holdout and prospective 2026/27 GW1 were not used.
- For every target game, both rate estimates were strictly past-only: prior-season rate aggregates games before the current NBA season; current-season rate aggregates games earlier in the current season. Actual target minutes are used only as exposure to isolate rate forecast error from minute forecast error.
- Prediction: `blend = prior_rate * (1 - n_current/(n_current + strength)) + current_rate * n_current/(n_current + strength)`, multiplied by actual minutes. This is a rate-only diagnostic, not an end-to-end PDK forecast validation.

## Pooled development results

| Prior strength | MAE (PDK; actual minutes fixed) | RMSE | Bias (predicted − actual) |
|---:|---:|---:|---:|
| 0 (current rate only) | 6.5774 | 8.8199 | -0.3313 |
| 2 | 6.4379 | 8.6184 | -0.3648 |
| 4 | 6.4032 | 8.5765 | -0.3979 |
| 6 | 6.3880 | 8.5600 | -0.4271 |
| 8 | 6.3806 | 8.5532 | -0.4528 |
| 12 | **6.3759** | **8.5521** | -0.4961 |
| 16 | 6.3773 | 8.5578 | -0.5314 |
| 24 | 6.3854 | 8.5750 | -0.5856 |
| 40 | 6.4044 | 8.6098 | -0.6566 |
| 80 | 6.4404 | 8.6693 | -0.7450 |

Strength 12 had the lowest pooled MAE and RMSE among the tested settings and was consistently near-optimal in all three development seasons. Improvement over strength 8 is small (MAE −0.0047 PDK; RMSE −0.0011), so this is a conservative parameter update, not a claim of a large model breakthrough. The slightly more negative bias should be monitored.

## Decision

- Set production `prior_strength` to 12, making a single current-season game worth 1/13 (7.7%) of the blend instead of 1/9 (11.1%). Ten current-season games have weight 45.5%; 30 games 71.4%.
- If no credible prior-season or market/role baseline exists, do not use the current-season rate as its own unshrunk prior. Fall back to independent market/role evidence; if no such evidence exists, leave the rate unavailable rather than extrapolating one hot game.
- This does not use the 2025/26 holdout for tuning and does not use prospective 2026/27 results. Re-evaluate the chosen strength only with future past-only folds.
