# Dunkest score reliability, strategy comparison, and evidence archive

Generated: 2026-10-14

## Findings

1. **Expanded recovered-score sensitivity:** 806 of 916 lineup-strategy rows can be scored by combining official weekly outcomes with explicitly labeled zero candidates, and rejoining coach base outcomes by season/date/team. There are 366 paired rounds with both strategies scoreable.
2. **Proxy strategy comparison:** the calibrated model beats the previous-five baseline by **44.17 PDK per round**, wins **75.4%** of paired rounds, and has a season-stratified bootstrap 95% interval of **[38.22, 50.11] PDK**.
3. **Player forecast calibration:** model MAE moves from 6.804 to 6.713, but RMSE moves from 9.963 to 9.977 and bias worsens slightly. The baseline improves more clearly (MAE 9.671 to 8.578; RMSE 13.135 to 11.905).
4. **Post-selection lineup score calibration:** the model's score MAE is 44.06 before calibration and 44.70 after calibration; RMSE improves from 57.99 to 57.57 and bias moves from +7.38 to -0.44. The previous-five baseline's MAE falls from 111.87 to 52.64 and its bias from +110.66 to +10.10.
5. **Pre-lock evidence archive:** run `20261014T103438Z_034cc8bc` has been copied into an immutable, hash-verified archive and registered. The independent freshness review found the fixture mapping was **49.69 hours old**, above the 36-hour limit, so this run is correctly marked ineligible for certified OOS evaluation.

## Why this does not prove strategy superiority

The recovered-score comparison assigns zero only in explicit proxy cases: a non-valid game record, or a team fixture without a player-game row. These cases cannot always be distinguished from a stale team assignment, missing identity link, or historical market eligibility error. The strategy also uses reconstructed CR/roles, a fixed coach-credit proxy, neutral coach multipliers, and zero transfer malus. The result is exploratory, not an official historical Dunkest backtest.

The strict observed-only comparison is too small to settle the question and did not corroborate the broad proxy result. Production model, solver, and transfer malus remain unchanged.

## Evidence infrastructure added

- `scripts/archive_dunkest_pre_lock_run_v1.py`: immutable run archive, SHA-256 inventory, freshness checks, and per-run registry record.
- `scripts/review_dunkest_pre_lock_archive_v1.py`: independent integrity and freshness recheck without mutating the archive.
- `scripts/run_dunkest_postmatch_oos_pipeline_v1.py`: guarded post-match collection and evaluation pipeline; it refuses uncertified archives unless diagnostic override is explicit.
- `src/dunkest/report/artifacts.py`: new runs also capture the fixture-mapping validation decision alongside the mapping itself.
- Unit tests cover archive integrity, immutability, stale/missing evidence, fixture source timestamps, and OOS gating.

## Next required work

1. Capture a fresh, provenance-bearing fixture mapping before the next prediction lock.
2. Archive that forecast and require every required input to be timestamped and fresh.
3. After all mapped fixtures finish, run the guarded post-match pipeline to archive official player/coach outcomes and produce a fixture-linked evaluation.
4. Accumulate multiple eligible rounds before comparing strategy variants with paired round-level bootstrap intervals. Do not deploy a challenger from proxy-only evidence.

## Detailed artifacts

- Recovered lineup outcomes: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v2.md`
- Past-only lineup-score calibration: `reports/audit/dunkest_recovered_lineup_postselection_calibration_20261014_v1.md`
- Archive review: `reports/audit/dunkest_pre_lock_archive_review_20261014_v1.md`
- Archive registry: `data/archives/pre_lock/registry/20261014T103438Z_034cc8bc.json`
