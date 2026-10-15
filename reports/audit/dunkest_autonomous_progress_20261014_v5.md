# Dunkest autonomous progress — 2026-10-14 V5

## Work completed

### 1. Repaired the prospective archive path

An audit found that `scripts/run_and_archive_prelock_v1.sh` invoked `archive_dunkest_prelock_run_v1.py` (no underscore), which wrote a different archive layout (`run_payload/`) without the immutable registry expected by the independent reviewer and post-match evaluation pipeline. This could have produced an archive that looked successful but could not enter the downstream certified evaluation workflow.

Changes:
- The capture script now invokes the canonical `scripts/archive_dunkest_pre_lock_run_v1.py` implementation and uses its actual CLI flag, `--max-age-hours`.
- The old no-underscore script is now a compatibility entry point to the canonical implementation, avoiding two competing archive formats.
- The data README documents the canonical command and flag.
- The canonical archiver now explicitly validates the target-gameweek fixture mapping: required identity/time/provenance columns, nonempty eligible slate, unique NBA game IDs, verified mappings, nonempty raw-payload hashes, valid UTC kickoffs, source retrieval before kickoff and run, and a maximum 36-hour pre-lock window.
- Fixture-validation details are stored in the archive manifest. Missing/invalid fixture evidence leaves `pre_lock_eligible=false`; it is never silently promoted to certified evidence.
- Added a regression test confirming valid mappings pass and unverified mappings fail the eligibility gate.

The existing archive format and registry are preserved; no collected prediction or snapshot data was overwritten.

### 2. Verification

- Full test suite: **383 passed in 8.68s** with `-W error::DeprecationWarning`.
- Focused archive/post-match tests: **30 passed** before the additional capture-script regression test was added; the final full suite includes it.
- `git diff --check`: passed.
- Capture shell syntax and Python compilation: passed.
- No commit or push performed.

### 3. Current capture timing

The capture script was run once as a safe preflight. It correctly refused to launch the model or create an archive because the earliest currently mapped fixture is `2026-10-20T00:00:00Z`, approximately **125.15 hours away**, exceeding the 36-hour limit. This is expected behavior, not a pipeline failure.

The first currently expected eligible time is **2026-10-18 12:00 UTC**, but the fixture map must be refreshed and revalidated when the script runs. The script should be launched only inside the permitted window and while the source market/availability inputs can be captured before the actual lock.

### 4. Still blocked / next steps

- Historical complete-lineup evaluation still lacks authentic historical pre-lock snapshots; no retrospective reconstruction is allowed.
- At the next valid window, run `bash scripts/run_and_archive_prelock_v1.sh`, inspect its `pre_lock_eligible` status, archive manifest and registry, then independently review hashes before treating it as certified.
- After the GW1 games finish and the safe post-game retrieval cutoff has passed, collect official player/coach outcomes and run `scripts/run_dunkest_postmatch_oos_pipeline_v1.py` against that exact immutable archive.
- Compare realized lineup scores only if fixture mapping, roster/credits, injuries/availability, coach CR, and official outcomes all pass their provenance and completeness gates.
- The 2026/27 GW1 final holdout remains frozen until **2026-10-23 12:00 UTC**. Do not tune against its realized results before the cutoff.

No model weights, lineup objective, availability eligibility, or coach calibration were changed in this pass.
