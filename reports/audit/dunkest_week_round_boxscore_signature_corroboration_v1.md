# Weekly-round exact boxscore signature corroboration (v1)

Generated UTC: 2026-10-12T14:15:39.452939+00:00

## Results

Cross-season candidates considered: **45**.
Rows matching an NBA game on the full 15-field boxscore signature: **19**.
Rows in the confirmed PHI–MIN multi-player cluster: **15**.
Isolated exact-signature candidates: **4**; of these, **2** also match official-history PDK at one-decimal precision.

## Clusters and isolated candidates

| Source file | NBA game date | Matchup | NBA game ID | Exact players | Players | PDK agrees with official history at 1dp |
|---|---|---|---|---:|---|---|
| `season_13_week_20_round_1_avg.parquet` | 2025-01-10 | BOS vs. SAC | 0022400528 | 1 | Jaden Springer | 1/1 |
| `season_5_week_40_round_3_avg.parquet` | 2022-03-14 | GSW vs. WAS | 0022101025 | 1 | Juan Toscano-Anderson | 0/1 |
| `season_5_week_43_round_2_avg.parquet` | 2021-11-27 | MIN @ PHI | 0022100292 | 7 | Anthony Edwards, D'Angelo Russell, Jaden McDaniels, Jarred Vanderbilt, Karl-Anthony Towns, Malik Beasley, Naz Reid | 7/7 |
| `season_5_week_43_round_2_avg.parquet` | 2021-11-27 | PHI vs. MIN | 0022100292 | 8 | Danny Green, Furkan Korkmaz, Isaiah Joe, Joel Embiid, Matisse Thybulle, Seth Curry, Tobias Harris, Tyrese Maxey | 8/8 |
| `season_5_week_53_round_2_avg.parquet` | 2022-02-04 | NOP @ DEN | 0022100794 | 1 | Nickeil Alexander-Walker | 1/1 |
| `season_9_week_40_round_2_avg.parquet` | 2024-02-10 | SAS @ BKN | 0022300750 | 1 | Sandro Mamukelashvili | 0/1 |

## Interpretation

Starting from 45 isolated cross-season candidates, compare the matching `tot` row against the candidate NBA game using player/team and 15 boxscore fields. Only gp=1 rows with exact field equality are included. The result identifies 15 rows from one confirmed game cluster and isolated exact-signature candidates; isolated rows are not automatically quarantined.

A row can match a boxscore signature from another season even when its PDK differs from the official player-history feed; that discrepancy remains unresolved and must not be repaired by substituting a proxy. Isolated matches should be reviewed rather than automatically excluded.

No source data, training target, production configuration, model, temporal split or backtest was modified.

CSV: `reports/audit/dunkest_week_round_boxscore_signature_corroboration_v1.csv`
JSON: `reports/audit/dunkest_week_round_boxscore_signature_corroboration_v1.json`
