# Training and inference feature schema audit — 2026-10-18 V1

Result: **PASS**

The selected features are the `FEATURE_COLS` that contain at least one finite value in certified 2020/21–2024/25 training rows. Inference coverage is counted only on production builder rows marked `is_inference`, using the archived 2025/26 player logs and official PDK overlay. This is a schema and data-availability check; it does not refit or select a model.

- Training rows: 93,766
- Selected training features: 56
- Production inference rows: 470
- Official PDK labels attached: 18,141
- Selected columns absent from inference: []
- Selected columns entirely null at inference: []

## Feature coverage

| Feature | Non-null next-game rows |
|---|---:|
| `pdk_mean_3` | 470 |
| `pdk_mean_5` | 470 |
| `pdk_mean_10` | 470 |
| `pdk_std_5` | 470 |
| `pdk_median_5` | 470 |
| `pdk_season_mean` | 456 |
| `min_mean_5` | 470 |
| `pdk_per_min_season` | 456 |
| `expected_pdk_minutes_model` | 456 |
| `pts_mean_5` | 470 |
| `reb_mean_5` | 470 |
| `ast_mean_5` | 470 |
| `stl_per36_5` | 470 |
| `blk_per36_5` | 470 |
| `tov_per36_5` | 470 |
| `oreb_per36_5` | 470 |
| `dreb_per36_5` | 470 |
| `fg3m_per36_5` | 470 |
| `fga_per36_5` | 470 |
| `rest_days` | 470 |
| `is_b2b` | 470 |
| `is_home` | 470 |
| `player_opp_pdk_per_min` | 456 |
| `player_opp_games` | 470 |
| `lag1_pdk` | 470 |
| `lag2_pdk` | 469 |
| `lag3_pdk` | 467 |
| `lag4_pdk` | 466 |
| `lag5_pdk` | 461 |
| `pdk_trend_3v10` | 470 |
| `min_trend_3v5` | 470 |
| `min_last_vs_prev5` | 470 |
| `abs_min_last_vs_prev5` | 470 |
| `min_std_5` | 469 |
| `min_zero_rate_5` | 470 |
| `team_changed_from_previous_game` | 470 |
| `team_history_known` | 470 |
| `team_games_since_change` | 470 |
| `lag1_nba_min` | 470 |
| `lag2_nba_min` | 469 |
| `lag3_nba_min` | 467 |
| `prev3_nba_min_mean` | 470 |
| `lag1_nba_pts` | 470 |
| `lag2_nba_pts` | 469 |
| `lag3_nba_pts` | 467 |
| `prev3_nba_pts_mean` | 470 |
| `lag1_nba_reb` | 470 |
| `lag2_nba_reb` | 469 |
| `lag3_nba_reb` | 467 |
| `prev3_nba_reb_mean` | 470 |
| `lag1_nba_ast` | 470 |
| `lag2_nba_ast` | 469 |
| `lag3_nba_ast` | 467 |
| `prev3_nba_ast_mean` | 470 |
| `history_games_before_target` | 470 |
| `nba_history_games_before_target` | 470 |

## Reproduction

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_training_inference_schema_20261018_v1.py
```

The source data is historical 2025/26 input, not the frozen 2026/27 GW1 test. No outcome metrics or model choices are computed here.
