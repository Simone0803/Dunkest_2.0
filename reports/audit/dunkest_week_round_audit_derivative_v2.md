# Weekly-round audit derivative — V2

Generated UTC: 2026-10-12T21:21:20.348204+00:00

## Purpose

This is an audit-only derivative with provenance and review flags. It is not a certified clean dataset, official per-game target table, or training input.

## Build summary

- Source files discovered: **1558**
- Files retained: **1556**
- Confirmed contaminated files excluded: **2**
- Rows excluded with those files: **236**
- Additional exact high-confidence rows removed from retained files: **4**
- Rows in derivative: **187330**
- Remaining isolated candidate rows flagged: **4**

## Safety rules

- No raw source file was changed.
- The two confirmed season-5/week-43/round-2 source files are omitted in full.
- Exact row-level register keys (season/week/round/player ID) are removed from other avg/tot source files.
- Isolated exact signatures with conflicting/invalid official PDK evidence remain flagged for review, not removed.
- Every retained row is marked audit_only_not_certified=True and eligible_for_training_from_this_derivative=False.
- Absence from current candidate scans is not evidence of clean season scope.

## Important limitations

The remaining rows are not certified as correctly season-scoped. Do not use this derivative for training, target construction, backtests, or production. The raw archive is unchanged.

Parquet: data/processed/dunkest_week_round_audit_derivative_v2.parquet
JSON: reports/audit/dunkest_week_round_audit_derivative_v2.json
File manifest CSV: reports/audit/dunkest_week_round_audit_derivative_v2_files.csv

Reproduce with: PYTHONPATH=src ./.venv/bin/python scripts/build_dunkest_week_round_audit_derivative_v2.py
