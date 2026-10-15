# Weekly-round audit derivative (v1)

Generated UTC: 2026-10-12T15:04:32.988791+00:00

## Purpose

This is an audit-only derivative with provenance and review flags. It is not a certified clean dataset, official per-game target table, or training input.

## Build summary

- Source files discovered: **1558**
- Files retained: **1556**
- Confirmed contaminated files excluded: **2**
- Rows excluded with those files: **236**
- Rows in derivative: **187334**
- Isolated exact-signature candidate rows flagged: **8**

## Excluded scopes

- `data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet` — 118 rows; confirmed PHI–MIN cross-season cluster.
- `data/raw/dunkest_history_v2/season_5_week_43_round_2_tot.parquet` — 118 rows; confirmed PHI–MIN cross-season cluster.

## Metadata added

- `source_file_audit`: original relative source path.
- `source_audit_status`: confirmed scope review status or `not_flagged_by_current_scan_not_certified`.
- `row_exact_full_boxscore_candidate` and `row_exact_candidate_player`: row-level flags for the four isolated exact-signature candidates.
- `audit_only_not_certified=True` and `eligible_for_training_from_this_derivative=False`: explicit safety guards.

## Important limitations

The remaining rows are not certified as correctly season-scoped. The endpoint root cause is unresolved, and current scans may miss other contaminated rows. Do not use this derivative for training, target construction, backtests, or production. The raw archive is unchanged.

Parquet: `data/processed/dunkest_week_round_audit_derivative_v1.parquet`
JSON: `reports/audit/dunkest_week_round_audit_derivative_v1.json`
File manifest CSV: `reports/audit/dunkest_week_round_audit_derivative_v1_files.csv`
