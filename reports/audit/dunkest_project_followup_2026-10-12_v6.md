# Dunkest project follow-up (v6)

Generated UTC: 2026-10-12T15:05:27.838803+00:00

## Outcome

The full project test suite passed: **213 passed, 0 failed**, with 6,800 warnings (mostly PuLP deprecations and one freshness warning). The endpoint scope audit completed 14 read-only requests with no errors.

## 1. Confirmed cross-season contamination

The public stats endpoint returns 118 rows for `season_id=5`, week 43, round 2 for both `avg` and `tot`; 15 players in each table match the exact PHI–MIN NBA game on 2021-11-27 (`0022100292`), which belongs to 2021/22 rather than the expected 2020/21. The same players have valid official season-7 history and all 15 PDK values agree at table precision.

Minimal requests and requests with explicit team, position, CR and sort filters produce identical payload hashes in both `avg` and `tot`. Thus, omitted optional filters in the collector do not explain this response. Season ID 7 queried for the same week/round returns 143 rows and a different payload. The explicit `season_id` parameter is present. The public response does not reveal whether the underlying cause is a stale cache, faulty join, or another backend issue; root cause remains unresolved.

Endpoint details: `reports/audit/dunkest_stats_endpoint_scope_v1.md`.

## 2. Quarantine and isolated review

Only `season_5_week_43_round_2_avg.parquet` and `_tot.parquet` remain marked for quarantine from any future clean derivative. Four isolated exact full-boxscore signature matches are explicitly documented as review-only: Jaden Springer (PDK agrees), Nickeil Alexander-Walker (agrees), Juan Toscano-Anderson (−3 vs +3, unresolved), and Sandro Mamukelashvili (2.1 vs 2.0, unresolved). A separate Sandro week-20 candidate differs in 3PA and is not an exact full-signature match. No singleton evidence is used to discard an entire file.

Manifest v2: `reports/audit/dunkest_week_round_quarantine_manifest_v2.md` (plus JSON/CSV).

## 3. Integrity and production safeguards

- No original Parquet was modified or deleted.
- No PDK targets, `gameValidForDunkest` flags, training features, models, production config, temporal splits or backtests were changed.
- No endpoint authentication was bypassed; requests were public read-only GETs.
- Weekly-round archive should not be treated as verified season-specific per-game target source until source behavior is reconciled.

## 3. Separate audit-only derivative created

Created `data/processed/dunkest_week_round_audit_derivative_v1.parquet` with **187,334 rows** from 1,556 retained source files. The two confirmed contaminated files (118 rows each) are excluded; all raw files remain untouched. All rows carry `audit_only_not_certified=True` and `eligible_for_training_from_this_derivative=False`. The four isolated exact-signature cases are row-flagged in their avg/tot tables (8 rows flagged total), and all 60 previously identified candidate files remain marked review-only. The other 1,496 files are labelled `not_flagged_by_current_scan_not_certified`, not clean.

Derivative report: `reports/audit/dunkest_week_round_audit_derivative_v1.md`; per-file provenance: `reports/audit/dunkest_week_round_audit_derivative_v1_files.csv`. This derivative is for auditing only, not training, official target construction, backtest labels or production use.

## 4. Final verification

After the derivative was built, the full test suite passed again: **213 passed, 0 failed**, 6,800 warnings. The derivative was re-opened after serialization and all safety-flag assertions passed.

## Next step

Create a separate, provenance-rich clean derivative only after enumerating source scopes: exclude the two confirmed contaminated files from that derivative, preserve all isolated candidates with review flags, and do not overwrite the raw archive. The endpoint root cause remains an open investigation.

JSON: `reports/audit/dunkest_project_followup_2026-10-12_v6.json`
