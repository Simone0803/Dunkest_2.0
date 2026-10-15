# Dunkest weekly-round cross-season integrity audit (v2)

Generated UTC: 2026-10-12T14:06:17.694466+00:00

## Method

Exact player name + team + PTS/REB/AST/STL/BLK/TOV/PLUS_MINUS signature (minutes excluded to avoid integer rounding differences) against NBA historical boxscores. A unique different-season match is a candidate; a cluster of >=5 players matching one different-season NBA game is strong evidence of source-scope contamination.

## Summary

- Weekly-round `avg` Parquets inspected: **779** (93,785 rows).
- Unique cross-season candidate rows: **45**.
- Multi-player clusters (at least 5 rows matching one NBA game in a different season): **2**.

| Table season ID | Expected NBA season | Rows | Exact expected-season matches | Cross-season candidates | Ambiguous seasons | No exact match |
|---:|---|---:|---:|---:|---:|---:|
| 5 | 2020-21 | 17,681 | 15,088 | 23 | 131 | 2,439 |
| 7 | 2021-22 | 18,422 | 15,376 | 1 | 153 | 2,892 |
| 9 | 2022-23 | 19,165 | 16,111 | 12 | 154 | 2,888 |
| 13 | 2023-24 | 18,927 | 16,142 | 7 | 184 | 2,594 |
| 19 | 2024-25 | 19,590 | 16,678 | 2 | 105 | 2,805 |

## Strongest cross-season clusters

| Table season | Source file | Expected season | Matched NBA season | NBA date | Matchup | Player rows | Evidence |
|---:|---|---|---|---|---|---:|---|
| 5 | `season_5_week_43_round_2_avg.parquet` | 2020-21 | 2021-22 | 2021-11-27 | PHI vs. MIN | 8 | multi_player_game_cluster |
| 5 | `season_5_week_43_round_2_avg.parquet` | 2020-21 | 2021-22 | 2021-11-27 | MIN @ PHI | 7 | multi_player_game_cluster |
| 13 | `season_13_week_12_round_1_avg.parquet` | 2023-24 | 2024-25 | 2025-04-11 | MEM @ DEN | 1 | isolated_candidate |
| 9 | `season_9_week_20_round_2_avg.parquet` | 2022-23 | 2023-24 | 2023-12-28 | SAS @ POR | 1 | isolated_candidate |
| 7 | `season_7_week_9_round_1_avg.parquet` | 2021-22 | 2022-23 |  |  | 1 | isolated_candidate |
| 9 | `season_9_week_10_round_2_avg.parquet` | 2022-23 | 2023-24 |  |  | 1 | isolated_candidate |
| 9 | `season_9_week_15_round_1_avg.parquet` | 2022-23 | 2023-24 |  |  | 1 | isolated_candidate |
| 9 | `season_9_week_1_round_1_avg.parquet` | 2022-23 | 2023-24 | 2024-03-18 | POR @ CHI | 1 | isolated_candidate |
| 9 | `season_9_week_27_round_1_avg.parquet` | 2022-23 | 2023-24 | 2023-12-28 | SAS @ POR | 1 | isolated_candidate |
| 5 | `season_5_week_53_round_2_avg.parquet` | 2020-21 | 2021-22 | 2022-02-04 | NOP @ DEN | 1 | isolated_candidate |
| 9 | `season_9_week_2_round_1_avg.parquet` | 2022-23 | 2023-24 | 2023-11-14 | ATL @ DET | 1 | isolated_candidate |
| 9 | `season_9_week_34_round_2_avg.parquet` | 2022-23 | 2018-19 | 2019-01-27 | DAL vs. TOR | 1 | isolated_candidate |
| 9 | `season_9_week_39_round_1_avg.parquet` | 2022-23 | 2024-25 | 2024-11-16 | DAL vs. SAS | 1 | isolated_candidate |
| 9 | `season_9_week_40_round_2_avg.parquet` | 2022-23 | 2023-24 | 2024-02-10 | SAS @ BKN | 1 | isolated_candidate |
| 9 | `season_9_week_43_round_1_avg.parquet` | 2022-23 | 2023-24 | 2023-11-13 | SAC vs. CLE | 1 | isolated_candidate |
| 9 | `season_9_week_4_round_1_avg.parquet` | 2022-23 | 2023-24 |  |  | 1 | isolated_candidate |
| 5 | `season_5_week_5_round_1_avg.parquet` | 2020-21 | 2022-23 |  |  | 1 | isolated_candidate |
| 5 | `season_5_week_52_round_2_avg.parquet` | 2020-21 | 2022-23 | 2022-11-17 | LAC vs. DET | 1 | isolated_candidate |
| 13 | `season_13_week_17_round_1_avg.parquet` | 2023-24 | 2019-20 |  |  | 1 | isolated_candidate |
| 5 | `season_5_week_48_round_2_avg.parquet` | 2020-21 | 2019-20 | 2019-11-08 | PHI @ DEN | 1 | isolated_candidate |

## Interpretation

A multi-player match to a single NBA game in a different season is stronger evidence than a lone score coincidence. The report preserves isolated candidates separately and does not automatically remove any row.
No exact match is not proof of corruption because of precision differences, missing values, or source corrections. Review candidate rows in the CSV before any filtering or rebuild.

Source Parquets and manifests were read only. No training labels, targets, models, production settings, temporal splits, or backtests were modified.

JSON details: `reports/audit/dunkest_week_round_cross_season_integrity_v2.json`
Candidate CSV: `reports/audit/dunkest_week_round_cross_season_integrity_v2.csv`
