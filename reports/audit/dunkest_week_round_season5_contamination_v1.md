# Verified cross-season rows in Dunkest weekly-round archive (v1)

Generated UTC: 2026-10-12T14:07:26.650305+00:00

## Finding

The file `data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet` is labelled stats `season_id=5` (expected 2020/21), but **15 player rows** match boxscore signatures from NBA game `0022100292` on **2021-11-27** (Philadelphia 76ers vs Minnesota Timberwolves), which belongs to 2021/22.
- Matching rows with a corresponding official player-history record under season ID 7: **15 / 15**.
- Rows marked `gameValidForDunkest=True` in that official history: **15 / 15**.
- PDK values equal after rounding the table and history values to one decimal: **14 / 15**.

## Player rows

| Player | Team | Weekly-table PDK | Season-7 official PDK | Valid flag | Difference |
|---|---|---:|---:|---|---:|
| Anthony Edwards | MIN | 26.5 | 26.5 | True | 0.000 |
| D'Angelo Russell | MIN | 45.0 | 45.0 | True | 0.000 |
| Jaden McDaniels | MIN | 6.5 | 6.5 | True | 0.000 |
| Jarred Vanderbilt | MIN | 18.0 | 18.0 | True | 0.000 |
| Karl-Anthony Towns | MIN | 34.5 | 34.5 | True | 0.000 |
| Malik Beasley | MIN | 4.8 | 4.75 | True | 0.050 |
| Naz Reid | MIN | 13.5 | 13.5 | True | 0.000 |
| Danny Green | PHI | 17.0 | 17.0 | True | 0.000 |
| Furkan Korkmaz | PHI | 2.8 | 2.75 | True | 0.050 |
| Isaiah Joe | PHI | 0.5 | 0.5 | True | 0.000 |
| Joel Embiid | PHI | 45.5 | 45.5 | True | 0.000 |
| Matisse Thybulle | PHI | 11.3 | 11.25 | True | 0.050 |
| Seth Curry | PHI | 10.0 | 10.0 | True | 0.000 |
| Tobias Harris | PHI | 20.8 | 20.75 | True | 0.050 |
| Tyrese Maxey | PHI | 14.0 | 14.0 | True | 0.000 |

## Consequence

This is not merely a single score coincidence: multiple players from the same game share the same exact boxscore signature and their official player-game PDK agrees at the weekly table's one-decimal precision. The season_id=5 weekly-round archive must therefore be treated as potentially contaminated at least in this scope. The finding does not establish that other files are contaminated, and isolated cross-season signature matches remain candidates rather than confirmed errors.

No source Parquet, manifest, training target, production configuration, model, temporal split, or backtest was changed.

CSV details: `reports/audit/dunkest_week_round_season5_contamination_v1.csv`
JSON details: `reports/audit/dunkest_week_round_season5_contamination_v1.json`
