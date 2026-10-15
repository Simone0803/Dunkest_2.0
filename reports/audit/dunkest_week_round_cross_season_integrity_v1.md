# Dunkest weekly-round cross-season integrity audit (v1)

Generated UTC: 2026-10-12T14:04:22.212524+00:00

## Method

Exact player name + team + integer minutes + PTS/REB/AST/STL/BLK/TOV/PLUS_MINUS signature against NBA historical boxscores. A unique different-season match is a candidate; a cluster of >=5 players matching one different-season NBA game is strong evidence of source-scope contamination.

## Summary

- Weekly-round `avg` Parquets inspected: **779** (93,785 rows).
- Unique cross-season candidate rows: **77**.
- Multi-player clusters (at least 5 rows matching one NBA game in a different season): **1**.

| Table season ID | Expected NBA season | Rows | Exact expected-season matches | Cross-season candidates | Ambiguous seasons | No exact match |
|---:|---|---:|---:|---:|---:|---:|
| 5 | 2020-21 | 17,681 | 8,338 | 23 | 34 | 9,286 |
| 7 | 2021-22 | 18,422 | 8,660 | 13 | 35 | 9,714 |
| 9 | 2022-23 | 19,165 | 8,911 | 17 | 30 | 10,207 |
| 13 | 2023-24 | 18,927 | 9,092 | 15 | 52 | 9,768 |
| 19 | 2024-25 | 19,590 | 9,220 | 9 | 28 | 10,333 |

## Strongest cross-season clusters

| Table season | Source file | Expected season | Matched NBA season | NBA date | Matchup | Player rows | Evidence |
|---:|---|---|---|---|---|---:|---|
| 5 | `season_5_week_43_round_2_avg.parquet` | 2020-21 | 2021-22 | 2021-11-27 | PHI vs. MIN | 6 | multi_player_game_cluster |
| 5 | `season_5_week_43_round_2_avg.parquet` | 2020-21 | 2021-22 | 2021-11-27 | MIN @ PHI | 3 | isolated_candidate |
| 13 | `season_13_week_11_round_1_avg.parquet` | 2023-24 | 2021-22 | 2022-01-21 | ORL vs. LAL | 1 | isolated_candidate |
| 7 | `season_7_week_48_round_2_avg.parquet` | 2021-22 | 2022-23 | 2022-12-11 | PHI vs. CHA | 1 | isolated_candidate |
| 7 | `season_7_week_59_round_3_avg.parquet` | 2021-22 | 2022-23 | 2023-02-27 | BOS @ NYK | 1 | isolated_candidate |
| 7 | `season_7_week_56_round_3_avg.parquet` | 2021-22 | 2020-21 | 2021-03-31 | MIN vs. NYK | 1 | isolated_candidate |
| 7 | `season_7_week_50_round_1_avg.parquet` | 2021-22 | 2022-23 | 2023-01-14 | CHA vs. BOS | 1 | isolated_candidate |
| 7 | `season_7_week_4_round_1_avg.parquet` | 2021-22 | 2022-23 | 2022-11-01 | BKN vs. CHI | 1 | isolated_candidate |
| 7 | `season_7_week_49_round_3_avg.parquet` | 2021-22 | 2022-23 |  |  | 1 | isolated_candidate |
| 7 | `season_7_week_49_round_1_avg.parquet` | 2021-22 | 2022-23 | 2023-02-14 | BOS @ MIL | 1 | isolated_candidate |
| 7 | `season_7_week_48_round_1_avg.parquet` | 2021-22 | 2020-21 | 2021-03-14 | CLE @ ATL | 1 | isolated_candidate |
| 5 | `season_5_week_51_round_1_avg.parquet` | 2020-21 | 2021-22 | 2022-01-12 | NYK vs. DAL | 1 | isolated_candidate |
| 7 | `season_7_week_42_round_1_avg.parquet` | 2021-22 | 2023-24 | 2024-03-05 | ORL @ CHA | 1 | isolated_candidate |
| 7 | `season_7_week_3_round_1_avg.parquet` | 2021-22 | 2020-21 | 2021-01-30 | CHA vs. MIL | 1 | isolated_candidate |
| 7 | `season_7_week_37_round_2_avg.parquet` | 2021-22 | 2020-21 |  |  | 1 | isolated_candidate |
| 5 | `season_5_week_8_round_1_avg.parquet` | 2020-21 | 2019-20 | 2019-11-13 | LAC @ HOU | 1 | isolated_candidate |
| 5 | `season_5_week_5_round_1_avg.parquet` | 2020-21 | 2022-23 | 2023-01-20 | ORL vs. NOP | 1 | isolated_candidate |
| 7 | `season_7_week_62_round_1_avg.parquet` | 2021-22 | 2020-21 | 2021-01-31 | LAC @ NYK | 1 | isolated_candidate |
| 7 | `season_7_week_6_round_3_avg.parquet` | 2021-22 | 2018-19 | 2019-02-08 | MIA @ SAC | 1 | isolated_candidate |
| 9 | `season_9_week_10_round_2_avg.parquet` | 2022-23 | 2023-24 | 2024-04-11 | SAC vs. NOP | 1 | isolated_candidate |

## Interpretation

A multi-player match to a single NBA game in a different season is stronger evidence than a lone score coincidence. The report preserves isolated candidates separately and does not automatically remove any row.
No exact match is not proof of corruption because of precision differences, missing values, or source corrections. Review candidate rows in the CSV before any filtering or rebuild.

Source Parquets and manifests were read only. No training labels, targets, models, production settings, temporal splits, or backtests were modified.

JSON details: `reports/audit/dunkest_week_round_cross_season_integrity_v1.json`
Candidate CSV: `reports/audit/dunkest_week_round_cross_season_integrity_v1.csv`
