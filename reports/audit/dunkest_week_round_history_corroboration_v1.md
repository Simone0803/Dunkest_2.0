# Weekly-round cross-season candidate corroboration (v1)

Generated UTC: 2026-10-12T14:14:28.355519+00:00

## Results

Candidate rows checked: **45**.
Confirmed 15-player cluster rows: **15**.
Isolated rows with same-date official history and PDK agreement at 1 decimal: **3**.
Same-date history exists but PDK differs: **19**.
No same-date history match or date unavailable: **8**.

## Corroborated isolated candidates

These rows warrant targeted review but are not grouped into a multi-player cluster, so this report does not automatically quarantine their files.

| File | Player | Table season | Candidate season | Date | Table PDK | Official PDK | Valid flag |
|---|---|---:|---|---|---:|---:|---|
| `season_13_week_20_round_1_avg.parquet` | Jaden Springer | 13 | 2024-25 | 2025-01-10 | 0.0 | 0.0 | True |
| `season_5_week_53_round_2_avg.parquet` | Nickeil Alexander-Walker | 5 | 2021-22 | 2022-02-04 | 13.0 | 13.0 | True |
| `season_9_week_20_round_2_avg.parquet` | Sandro Mamukelashvili | 9 | 2023-24 | 2023-12-28 | -1.0 | -0.95 | True |

## Interpretation

A same-player/date official-history match plus PDK agreement at one-decimal table precision corroborates a cross-season candidate, but isolated rows are still tracked separately from the confirmed multi-player cluster. PDK mismatches and missing history rows are unresolved, not automatically labelled errors.

Source data was read only. No source Parquet, training target, validity flag, model, production configuration, temporal split or backtest was changed.

CSV: `reports/audit/dunkest_week_round_history_corroboration_v1.csv`
JSON: `reports/audit/dunkest_week_round_history_corroboration_v1.json`
