# Dunkest player-profile games API verification

Generated: 2026-10-12T11:50:32.574304+00:00

Endpoint: `https://www.dunkest.com/api/player/games`

## Exact comparison for Luka Dončić (Dunkest player ID 127)

| Season | API rows | Saved rows | Matched game IDs | Field mismatches | Valid=True | Valid=False |
|---|---:|---:|---:|---:|---:|---:|
| 2018-19 | 72 | 72 | 72 | 0 | 0 | 72 |
| 2019-20 | 61 | 61 | 61 | 0 | 0 | 61 |
| 2024-25 | 50 | 50 | 50 | 0 | 39 | 11 |
| 2025-26 | 64 | 64 | 64 | 0 | 50 | 14 |

## Historical validity-flag distribution

| Season archive | Rows | True | False | Missing | Date range |
|---|---:|---:|---:|---:|---|
| `official_dunkest_player_games_2018-19_season_id_1.parquet` | 26094 | 0 | 26094 | 0 | 2018-10-16 – 2019-04-10 |
| `official_dunkest_player_games_2019-20_season_id_3.parquet` | 22384 | 0 | 22384 | 0 | 2019-10-22 – 2020-08-14 |
| `official_dunkest_player_games_2020-21_season_id_5.parquet` | 22568 | 17662 | 4906 | 0 | 2020-12-22 – 2021-05-16 |
| `official_dunkest_player_games_2021-22_season_id_7.parquet` | 24424 | 18422 | 6002 | 0 | 2021-10-19 – 2022-04-10 |
| `official_dunkest_player_games_2022-23_season_id_9.parquet` | 25265 | 19165 | 6100 | 0 | 2022-10-18 – 2023-04-09 |
| `official_dunkest_player_games_2023-24_season_id_13.parquet` | 25732 | 18927 | 6805 | 0 | 2023-10-24 – 2024-04-14 |
| `official_dunkest_player_games_2024-25_season_id_19.parquet` | 25631 | 19590 | 6041 | 0 | 2024-10-22 – 2025-04-13 |

## Interpretation

- The profile page and the historical collector use the same public per-game endpoint, `/api/player/games`, with `player_id` and `season_id` parameters.
- For the four tested seasons, every Luka row and every API field matches the already-saved local archive exactly. This verifies the source path; it does not constitute a new historical scrape.
- Preserve `gameValidForDunkest` as a raw field. Do not use it as a universal target filter: every row in the 2018-19 and 2019-20 archives is marked `False`, whereas later archives contain both values.
- No production files, training data, or validation splits were changed.
