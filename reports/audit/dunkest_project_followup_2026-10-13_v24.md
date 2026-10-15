# Dunkest project follow-up — 2026-10-13 (v24)

This update extends v23 with a read-only inventory of historical pre-lock archives and a deeper code-path audit. Earlier experiments and decisions remain in v22/v23 and their linked reports.

## 16. Historical pre-lock archive inventory

Added and ran:
- `scripts/audit_dunkest_prelock_archive_inventory_v1.py`
- `reports/audit/dunkest_prelock_archive_inventory_20261013_v1.md`
- `reports/audit/dunkest_prelock_archive_inventory_20261013_v1.csv`

The inventory scans only filenames and sidecar metadata in `data/processed`. It deliberately excludes season ID 25 (2025/26 holdout) and season ID 26 (frozen 2026/27 prospective GW1). It does not load model predictions or evaluate forecast performance.

Across historical season IDs 1, 3, 5, 7, 9, 13 and 19, the scan found **zero season-specific files** in each of these six required families: fixture mapping, player-market/CR snapshot, injury snapshot, coach market, player-week outcomes and coach outcomes. This means there is no season-keyed archive in the expected processed-data layout that can substantiate the full historical pre-lock information set.

This result is consistent with the earlier `historical_dunkest_market_snapshot_inventory_v1.md`: the historical `dunkest_history` and `dunkest_history_v2` directories contain extensive week/round outcomes, but the `avg` and `tot` tables are not independent pre-lock snapshots. That audit found 31 run-level `pre_match_snapshot` bundles, all from the current 2026/27 opener capture period, and no non-2026/27 run-level bundles. The older weekly archives are useful for realized outcomes and leakage-safe player-form features, not for reconstructing exact historical market availability.

The remaining season-ambiguous files are not substitutes. For example, legacy player tables and opening market carry sidecar ingestion times in late September 2026, while the generic injury file was written in October 2026. These timestamps record when this pipeline fetched/wrote the files, not when the source information was originally published or whether it was available before a historical Dunkest lock. The generic coach GW35 artifact has zero rows. They cannot establish historical roster, CR, injury, coach-credit or fixture state.

## 17. Code-path findings confirmed against the local working tree

1. **Missing player outcomes can become zero.** In `src/dunkest/data/access.py`, when the target-week table is non-empty, the current merge fills missing player rows with `0.0` for `actual_pdk`. The `gameweek_stats_available` flag is global to the table, not a per-player observation flag. A missing player row is therefore not distinguished from an observed zero outcome.
2. **Readiness checks file structure, not snapshot availability time.** `check_backtest_readiness` validates fixture mapping retrieval time against game time, but roster/CR, injuries and coach-market checks mainly test file presence and columns. They do not compare each sidecar's `fetched_at` against a documented prediction cutoff. A valid schema does not prove a pre-lock snapshot.
3. **An empty injury result is indistinguishable from a missing collection.** `save_injury_snapshot` returns without writing when the input is empty. Readiness then treats the missing file as failure, but there is no durable record showing whether collection completed successfully with zero reported injuries.
4. **Coach snapshot readiness is not full market completeness.** The check requires a non-empty table and selected fixture-linkage columns, but does not prove complete score-bearing team coverage, valid opponent CR for every scored coach, or pre-cutoff availability.
5. **Actual-result readiness is too coarse for row-level evidence.** The gate accepts any non-null player target plus a global availability flag and checks fixture IDs, but does not establish the observation status of every player-target row. This is especially problematic alongside the zero-fill behavior above.

## 18. Decision and next implementation order

No historical lineup model should be promoted on the basis of these archives. The data limitation is now demonstrated in the local processed-data inventory, not just inferred from failed backtests.

The safe implementation sequence is:
1. Add a per-player target-observed/target-valid flag and stop silently converting unmatched target rows to zero. Preserve missing as unknown unless a source explicitly certifies a zero.
2. Extend snapshot metadata with explicit collection status, source publication/retrieval timestamps, and the actual prediction cutoff; require temporal validation for player market, injury and coach snapshots.
3. Persist successful empty injury collections separately from failed or skipped collections.
4. Validate coach market coverage against the verified score-bearing fixture universe and require the opponent-credit evidence needed for realized-score reconstruction.
5. Add focused unit tests for missing-vs-zero labels, stale/post-cutoff snapshots, empty-vs-failed injury collections, and incomplete coach coverage.
6. Only after these gates are tested, rerun readiness on historical seasons. Do not backfill gaps with current data, and do not use the frozen 2026/27 GW1 run before 2026-10-23 12:00 UTC.

## Verification and safety

- Archive inventory script executed successfully and produced Markdown/CSV; `py_compile` passed.
- Focused existing tests passed: `test_realized_scores.py`, `test_backtest_market_snapshot.py`, `test_temporal_validation.py` — **15 passed**.
- `git diff --check` passed.
- No production source/configuration was changed in this continuation.
- No model was trained or tuned; no 2025/26 holdout or frozen 2026/27 GW1 predictions were evaluated.
- No commit or push was performed.
- Existing tracked changes and the many pre-existing untracked research artifacts were preserved.
