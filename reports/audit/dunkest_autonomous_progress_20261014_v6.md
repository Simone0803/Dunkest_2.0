# Dunkest autonomous progress — 2026-10-14 v6

## Scope of this pass

Continued the bounded historical-source recovery and strengthened the prospective pre-lock archive gate. No model weights were tuned and no prediction test set was used for tuning.

## Implemented

- Added `snapshot_content_validation()` to `scripts/archive_dunkest_pre_lock_run_v1.py`.
- The gate checks readable schemas and plausible coverage for the player market, player credits, injuries, availability and coach market; checks that player credits/injuries/coaches are linked to the target gameweek; checks availability observation timestamps; and requires a complete 30-team coach market.
- A structurally invalid run can still be archived for diagnosis, but it cannot be marked pre-lock eligible.
- Updated `scripts/review_dunkest_pre_lock_archive_v1.py` to independently repeat the content checks as well as hashes, freshness and fixture checks.
- Preserved compatibility with older immutable registry records: the new registry field is written only when the archive manifest contains the corresponding validation report.
- Added tests preventing GW1 snapshots from satisfying a GW2 archive, rejecting truncated player markets, and rejecting wrong-round credits/incomplete coach coverage.
- Added `reports/audit/dunkest_historical_listone_source_recovery_20261014_v1.md` with the verified state of the two historical public listone links investigated. No spreadsheet was downloaded or mislabeled as historical.

## Verification

- Focused tests: **17 passed**.
- Full test suite: **406 passed in 8.95s** using `PYTHONPATH=src ./.venv/bin/python -m pytest -q -W error::DeprecationWarning`.
- `git diff --check`: passed.
- Content checks against the latest GW1 run `20261014T175113Z_7c1f0803`: all five non-fixture snapshots passed structural validation. This does not make the run certifiable: its fixture snapshot is outside the pre-lock time window, and the run occurred about 123 hours before earliest kickoff.
- Independently re-reviewed the archived run `20261014T103438Z_034cc8bc` read-only: hashes remain intact, but it remains ineligible because the fixture snapshot is stale and the run was too early. No archive was mutated.

## Historical-source finding

The 2024/25 playoff article's download link currently opens a Google Sheet titled **Listone Dunkest Fantasy NBA 2026/27**, so it is not usable as historical evidence. The 2023/24 article's spreadsheet link returns **410 Gone**. A third-party Scribd upload titled 2024/25 was also rejected because its contents include later-season names/team assignments. A read-only local filename scan found no relevant historical listone spreadsheet, and the similarly named tar archive contains code only. No suspect file was imported. The source inventory remains a candidate inventory, not a certified count of complete historical rounds.

## Constraints still in force

- Do not reconstruct missing historical credits, injuries, coach market or transfer malus as certified data.
- Keep the prospective GW1 2026/27 test frozen until **2026-10-23 12:00 UTC**.
- The pre-lock runner must not be run before the fixture window opens. Based on the currently recorded earliest kickoff of **2026-10-20 00:00 UTC**, the 36-hour window begins at **2026-10-18 12:00 UTC**; recheck the latest fixture map before execution.
- No commit, push, staging, destructive cleanup or broad worktree reset was performed.
