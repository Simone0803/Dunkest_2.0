# Dunkest 2.0 completion and prospective readiness — 2026-10-18 V1

## Executive summary

The production player forecast path, historical training evidence, lineup optimizer, and prospective collection/evaluation flow were checked against the current working tree and prior audit artifacts. The full test suite passes. A new chronological evaluation of the current multi-season adapter shows a small, consistent improvement from using the certified earlier seasons with the existing low-history weighting. This supports keeping the current multi-season approach; it does not establish that any fantasy lineup strategy scores better in real play.

The 2026/27 GW1 test remains untouched. The available prediction runs and four standalone input snapshots are too early and their fixture mapping was retrieved on 2026-10-12. The earliest mapped tip-off is 2026-10-20 00:00 UTC. The 36-hour capture window opens at 2026-10-18 12:00 UTC. No certified GW1 pre-lock archive or post-match actuals exist yet.

## Initial state and safeguards

- Repository: `/Users/simone/Documents/Dunkest`.
- Branch: `codex/claude-audit-hardening-20261015`.
- HEAD at inspection: `de36ce0` (`Add Dunkest validation and calibration experiments`).
- The working tree already contained uncommitted changes to the player feature builder, multi-season adapter, predictor, tests, and several new audit artifacts. These were preserved. No reset, cleanup, commit or push was performed. The one known versioned-report regeneration is documented below.
- A process-list check was attempted with `ps` and `pgrep`; the host denied global process enumeration (`operation not permitted` / `Cannot get process list`). The one-shot capture waiter launched in this session is tracked separately through its live execution handle; unrelated pre-existing process state remains unknown.
- The prospective GW1 result/strategy comparison was not run, and no prospective result data was read for tuning.

## Essential inventory

### Already implemented and verified

- `config/season_opener.yaml` selects `target_pdk_official` and the multi-season trainer. The GW1 path loads prior-season logs for inference and trains the supervised model from certified 2020/21–2024/25 official PDK rows. The documented dataset contains 93,766 eligible training rows for those seasons; the broader verified dataset contains 112,178 rows through 2025/26, which is excluded from the production GW1 training cutoff.
- Automatic target selection now refuses to fall back silently to proxy PDK when official labels are absent or below the configured threshold. Proxy training requires an explicit selection.
- The working-tree changes add one shared, past-only, official-PDK definition for four history features used by the multi-season adapter and inference builder. Target leakage, ambiguous duplicate player/date ordering, and proxy fallback for these features are guarded by tests.
- Player walk-forward and feature experiments already cover the previous-10 baseline, production ensemble, multi-season training, official/proxy history, hyperparameters, feature families, minutes, player cohorts, and score tails. The production hyperparameter audit kept the existing production model because alternatives had mixed, marginal results.
- Coach rules, matchup simulation, score forecasting and calibration have extensive historical walk-forward and sensitivity reports. Existing measured coach simulation results are at neutral CR: Monte Carlo MAE 15.202 versus 16.073 for direct score prediction and 16.596 for previous-10. These reconstructed/neutral-credit results do not certify official price-adjusted coach accuracy.
- Plusvalenza training uses 93,744 official rows from verified 2020/21–2024/25 seasons, including 6,118 negative PDK records. Its prior walk-forward report measured ΔCR MAE 0.062556 versus 0.181359 for a simple baseline. The optimizer values expected plusvalenza through a conservative one-step CR shadow-price proxy; this is not a validated multi-week strategy.
- The MILP implements the roster, budget, role, team, coach, captain, slot, transfer-malus and top-k constraints. It has independent lineup/scoring checks and deterministic, synthetic edge-case tests. Its strategy superiority is not empirically certified.
- Immutable pre-lock archiving, integrity review, a pre-lock registry, a post-match collector, realized-score evaluation, and readiness gates exist. The post-match evaluator rejects incomplete player/coach outcomes and does not turn unknown scores into zero. Normal capture/collection scripts contain no interactive prompt; remaining `input()` calls are in browser/UI diagnostic scripts.

### Improved or further validated in this turn

- Updated `save_pre_match_snapshot` and `save_post_match_snapshot` to write into a private sibling staging directory and publish the complete archive with one directory rename. Interrupted writes remove the staging directory and leave no visible partial archive.
- Added Git branch/commit and a source-tree SHA-256 fingerprint to the standalone pre- and post-match archive manifests. Those reserved fields cannot be replaced by caller metadata.
- Added failure-path tests that simulate a keyboard interruption during pre-match writing and a disk error partway through post-match writing.
- Hardened realized roster scoring so missing player-result mappings and missing or nonnumeric coach actuals are classified as incomplete instead of raising. Added regression coverage for absent mappings, `None`, invalid text and NaN coach actuals.
- Fixed two model-manifest provenance gaps: the enriched historical NBA minutes-label dataset and the selected official PDK inference overlay are now SHA-256 fingerprinted. Run metadata records the overlay source and attached label count; model details record the minutes-label source and matched historical row count.
- Completed the source-file audit for plusvalenza and rookie model inputs: manifests now fingerprint the official rookie PDK labels and all versioned multi-season plusvalenza cache files, including the per-season caches discovered by the loader. Coach inputs are covered by the captured live market, coach configuration, fixtures and team logs.
- Closed the post-match evidence provenance gap: the collector's immutable result manifest and audit now include SHA-256 and byte size for all eight input files used to build outcomes, including official player results, final team/player logs, frozen run manifest/predictions and the archived fixture and coach/player markets. Hashes are captured before and after collection; changed inputs fail closed. Each collection attempt has a unique ID and audit filenames, so retries preserve earlier diagnostics. Regression tests verify retries retain earlier outputs and a changed official results file prevents archive publication.
- Post-match archive schema 2 adds an append-only sibling registry that authenticates the result manifest and both result-table hashes. The evaluator verifies the registry before trusting manifest timestamps or coverage metadata. Tests tamper with the retrieval timestamp and verify rejection; legacy schema 1 remains readable for diagnostics but cannot yield certified-ready metrics.
- Fixed a post-match safety gap found during the current source audit: the collector previously fingerprinted and loaded official outcome files before checking the safe retrieval cutoff. It now derives the cutoff from the frozen fixture mapping first and, when early, writes only a timing diagnostic with `outcome_files_read=false`; official result files are not statted, hashed or parsed. The regression test forbids both fingerprinting and reading outcomes before cutoff.
- Added an orchestration regression proving the end-to-end post-match runner stops when the collector returns the early-cutoff diagnostic and does not invoke evaluation.
- The evaluator also rejects result timestamps more than five minutes in the future, even when the test archive registry correctly authenticates that timestamp.
- If post-match registry creation fails after the result directory is staged, the writer removes that newly created directory; a regression test verifies no unregistered archive is left behind.
- The pre-lock archiver now applies the same rollback when its new bundle cannot be registered, while leaving existing archives intact; its failure-path test verifies no published directory or partial registry remains.
- Added a direct freshness regression proving a market sidecar timestamped after the forecast is classified `fetched_after_prediction` and cannot be certified.
- Evaluation JSON, Markdown and lineup CSV now also receive unique evaluation IDs instead of overwriting the prior report for the same frozen run. A regression test repeats the evaluator and verifies the first evaluation file remains byte-identical.
- Added a backtest-orchestrator wiring test that verifies the certified archive validation step is followed by collection and that the exact immutable results archive is passed to evaluation for the same frozen run.
- Hardened the pre-lock wrapper to reject zero or multiple new forecast runs after launch, refuse launch at or after the earliest tip-off, and reject a `DUNKEST_MAX_PRELOCK_HOURS` override above 36 hours. The existing capture-script test now asserts these safeguards. Shell syntax validation passed; the 09:44 UTC checks rejected a 37-hour override and the default 38.25-hours-to-tip-off case before scraping.
- Rechecked the live preflight at 10:03 UTC: it found the latest fixture-linked prior run `20261016T073129Z_8c917889`, computed 37.94 hours to the 2026-10-20 00:00 UTC tip-off, and exited before the model/scrape step. A disk inventory still shows only the old `20261014T103438Z_034cc8bc` registry entry, marked ineligible; no capture or archive was created.
- Rechecked at 10:09 UTC: the same prior run and 2026-10-20 00:00 UTC tip-off produced 37.85 hours to kickoff, so the wrapper exited before model/scrape. The registry still contains only the October 14 run, with `pre_lock_eligible=false` and `eligibility_status=incomplete_evidence`.
- Rechecked at 10:30 UTC: the preflight found 37.48 hours to the earliest kickoff and exited before model/scrape; no capture or archive was created.
- Rechecked at 10:45 UTC: the same preflight found 37.23 hours to kickoff and exited before model/scrape; no capture or archive was created.
- Rechecked at 10:57 UTC: the preflight found 37.04 hours to kickoff and exited before model/scrape. The registry inventory still contains only the ineligible October 14 run.
- Rechecked at 10:59:54 UTC: the preflight found 37.00 hours to kickoff and exited before model/scrape. The registry still contains only the same ineligible run.
- Rechecked at 11:00 UTC: the preflight found 36.99 hours to kickoff and exited before model/scrape. A registry inventory still shows only the ineligible October 14 run.
- At 11:07 UTC, confirmed the 36-hour capture window had not opened and the registry still contained only the ineligible October 14 run. A single delayed invocation of the guarded wrapper is active for 12:00 UTC; no prediction run or archive has been created by that wait process.
- At 11:07:50 UTC, a direct safe-gate invocation found 36.87 hours to the earliest kickoff and exited before model or scrape; the output explicitly confirmed that no run or archive was created.
- At 11:22 UTC, the capture waiter remained live and the registry still contained only the ineligible October 14 run; no new prediction run or archive had been created.
- At 11:23 UTC, a fresh guarded preflight found 36.61 hours to kickoff and exited before model/scrape; it confirmed no new prediction run or archive was created.
- At 11:31 UTC, a fresh guarded preflight found 36.47 hours to kickoff and exited before model/scrape; the registry still contained only the ineligible October 14 run.
- At 11:36 UTC, a fresh guarded preflight found 36.39 hours to kickoff and exited before model/scrape; it confirmed no new prediction run or archive was created.
- Added an output-stem option to the existing multi-season walk-forward validator so reruns can create versioned artifacts without overwriting previous results.
- Verified the selected training-to-inference schema on the actual certified 2020/21–2024/25 adapter and the production feature builder using archived 2025/26 logs plus their official PDK overlay. All 56 features selected from 93,766 training rows exist and have non-null coverage among the 470 next-game inference rows. This checks feature availability, not predictive quality; the 2026/27 GW1 test was not loaded.
- Hardened the training/inference schema audit with `--output-stem` and a refusal to overwrite existing report files. A separately named V2 rerun reproduced the same 93,766 training rows, 56 selected features, and 470 inference rows; it also reports the 48 unavailable official PDK overlay labels among 24,100 candidate rows.
- During a usage check, the schema audit was invoked with unsupported `--help` before the safeguard existed, so it ran and regenerated its fixed-name V1 JSON and Markdown reports. The V1 output bytes were not preserved, and I cannot claim that no versioned report was overwritten. Its regenerated measurements match the documented results; the V2 run now preserves a separately named record. The optimizer audit's existing versioned-output guard prevented its fixed-name outputs from being regenerated.
- Ran a deterministic optimizer sensitivity experiment on a fixed synthetic pool (40 players, two coaches, seed 20261018). All five expected-value/risk-adjusted solves were optimal and passed independent solution validation. The risk-adjusted objective decreased monotonically as lambda rose from 0.05 to 0.50; reported expected net PDK moved from 256.555 under expected value to 253.710 at lambda 0.50. The selections changed as risk aversion rose. This verifies objective sensitivity and scoring consistency only; it does not support a real-data strategy choice.
- Ran the current multi-season adapter and production trainer on official labels, with temporal test folds 2022/23–2024/25. The 2025/26 and 2026/27 prospective data were excluded.
- Repeated the three-fold player walk-forward with a new V2 output stem. All three low-history weighted fold MAE improvements over previous-season-only matched V1 to displayed precision. Across 173,046 keyed prediction rows, maximum absolute V1/V2 prediction difference was 2.14e-14; maximum metric difference was 1.78e-15. The rerun's JSON records official labels, folds 2022/23–2024/25, exclusion of 2025/26, untouched 2026/27 GW1 and `production_changed=false`.
- Re-audited the current coach scoring, plusvalenza estimator and MILP integration against source and existing versioned audits. Coach credit multipliers remain deterministic rule arithmetic; plusvalenza training reconstructs pre-game CR, retains valid negative PDK outcomes and uses past-only walk-forward residuals; gain/loss probability calibration remains conversion-only. The optimizer still values plusvalenza through a one-step shadow-price proxy, not a validated multi-gameweek policy. Focused current-tree coverage passed **60 tests** across `test_role_minutes_projection.py`, `test_optimizer_smoke.py`, `test_coach_simulation.py` and `test_rules_pdk.py`.
- Filled a coach rule-test gap with a table-driven check for every positive and negative margin-bucket boundary, validating both scalar and vectorized scoring paths against the explicit score table. The added test passes.

### Impossible to certify without new prospective data

- No historical round archive establishes the actual pre-lock player prices, credit budget, availability, coach market, transfer state and time-valid lineup universe for every past Dunkest gameweek. The historical full-roster strategy backtest is therefore unidentifiable and will not be reconstructed.
- Real 2026/27 lineup performance cannot be assessed until a fresh pre-lock run is captured and archived, then its official player and coach actuals are complete and fixture-linked after the safe post-game cutoff.
- No strategy can be declared superior from synthetic fixtures, incomplete historical proxies, or GW1 alone.

## Current multi-season player evaluation

Command:

```bash
PYTHONPATH=src .venv/bin/python scripts/validate_dunkest_multiseason_ensemble_walk_forward_v1.py --output-stem dunkest_multiseason_production_ensemble_walk_forward_20261018_v1
PYTHONPATH=src .venv/bin/python scripts/validate_dunkest_multiseason_ensemble_walk_forward_v1.py --output-stem dunkest_multiseason_production_ensemble_walk_forward_20261018_v2
```

The experiment used identical official targets and folds for all training windows. Results cover 57,682 player-games across 2022/23, 2023/24 and 2024/25.

| Training variant | Weighted MAE | Weighted RMSE | Weighted bias |
|---|---:|---:|---:|
| Previous season only | 7.5359 | 9.7802 | +0.0120 |
| All prior seasons | 7.5191 | 9.7667 | -0.0628 |
| All prior seasons, existing low-history weighting | 7.5121 | 9.7647 | -0.1116 |

Paired comparison against previous-season-only, resampling whole game dates within each held-out season (10,000 replicates, seed 20261018):

| Variant | 2022/23 Δ MAE | 2023/24 Δ MAE | 2024/25 Δ MAE | Equal-season macro Δ MAE | 95% interval |
|---|---:|---:|---:|---:|---:|
| All prior seasons | -0.0203 | -0.0278 | -0.0028 | -0.0170 | [-0.0227, -0.0057] |
| All prior seasons, low-history weighted | -0.0239 | -0.0424 | -0.0058 | -0.0240 | [-0.0325, -0.0145] |

The low-history-weighted candidate is marginally better in each fold, with a small pooled gain. It remains validation evidence from inspected project data, not a pristine final holdout. No model weights or production configuration were changed as a result.

The V2 rerun reproduces the per-fold comparisons: weighted low-history MAE was 7.5193, 7.4985, and 7.5183 for 2022/23–2024/25; previous-season-only was 7.5432, 7.5408, and 7.5241. V1/V2 keyed predictions agree within 2.14e-14 absolute difference, with no material numeric divergence.

### Direct simple-baseline comparison

To cover simple recent-form and rate baselines on the exact same held-out rows, the saved predictions were joined back to the certified training adapter and official NBA minute labels. No model was refit. Direct means are computed from strictly prior official PDK only; the per-minute estimate multiplies the past official PDK/minute rate by the prior-five NBA minute mean. The model is scored on the same finite-baseline rows.

| Baseline | Rows / coverage | Baseline MAE | Model MAE on same rows | Δ MAE (model − baseline) | 95% date-cluster interval, equal-season macro |
|---|---:|---:|---:|---:|---:|
| Previous 3 official PDK mean | 57,433 / 99.6% | 8.3193 | 7.5209 | -0.7983 | [-0.8347, -0.7293] |
| Previous 5 official PDK mean | 57,433 / 99.6% | 7.9749 | 7.5209 | -0.4540 | [-0.4990, -0.4146] |
| Previous 10 official PDK mean | 57,433 / 99.6% | 7.7673 | 7.5209 | -0.2463 | [-0.2785, -0.2193] |
| Past-season official PDK mean | 57,433 / 99.6% | 7.7151 | 7.5209 | -0.1941 | [-0.2199, -0.1558] |
| Past official PDK/min × previous-5 NBA minutes | 57,425 / 99.6% | 7.6855 | 7.5215 | -0.1640 | [-0.1921, -0.1197] |

Each baseline comparison favored the model in all three folds. The result supports the player-score model over these simple baselines on the available historical data. It still does not validate a fantasy lineup strategy, and the multi-season weighted improvement over previous-season-only remains small.

Reproduction:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_multiseason_temporal_baselines_20261018_v1.py
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_training_inference_schema_20261018_v1.py --output-stem dunkest_training_inference_schema_20261018_v2
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_optimizer_synthetic_risk_20261018_v1.py
```

The schema audit reports the selected training feature columns, their inference coverage, and any columns missing or entirely null at inference. The rerun input and output manifest is `reports/audit/dunkest_training_inference_schema_20261018_v2.json`.

Existing complementary result: the 2026-10-15 exact production-trainer audit reported pooled MAE 7.5524 against 7.7756 for previous-10 on the same three temporal seasons. Its 2025/26 fold is not used as a clean holdout. The historical RF V3 experiment also found a modest improvement over previous-10, but retained that model as experimental rather than production.

## Prospective archive readiness

- Earliest GW1 fixture: **2026-10-20 00:00 UTC**; latest mapped fixture: **2026-10-22 00:00 UTC**.
- Existing GW1 prediction runs: **86**; latest manifest timestamp: **2026-10-16 07:31:29 UTC**. These are not automatically certified archives.
- Standalone GW1 input snapshots: **4**, dated 2026-10-15 and 2026-10-16. Each contains 16 fixture rows and integrity hashes. The earliest source retrieval time in their fixture mappings is **2026-10-12 08:53:22 UTC**, outside the 36-hour freshness window.
- The only record in `data/archives/pre_lock/registry` is run `20261014T103438Z_034cc8bc`, marked ineligible. Its existing review found a 49.7-hour-old fixture mapping and a capture more than 133 hours before tip-off.
- Therefore, **zero available GW1 artifacts are certified as fresh pre-lock evidence**. The scheduled 36-hour window for the earliest fixture opens at **2026-10-18 12:00 UTC**. The existing `scripts/run_and_archive_prelock_v1.sh` must refresh and independently validate the fixture map and all source snapshots before it creates a certified archive.
- At **2026-10-18 09:31 UTC**, the pre-lock command was run as a safe gate check. It reported 38.47 hours until tip-off, exited before the model/scrape step, and confirmed that no run or archive was created.
- At **2026-10-18 09:44 UTC**, the gate was rechecked after updating the wrapper to require exactly one newly created prediction run before archiving and reject launch at or after tip-off; it reported 38.26 hours until tip-off and exited before the model/scrape step. At 09:44:45 UTC, a 37-hour environment override was also rejected and the default gate again exited at 38.25 hours. No run or archive was created. `bash -n scripts/run_and_archive_prelock_v1.sh` passed.
- No post-match archive exists yet, which is expected before the first fixture. The collector refuses to start before its safe retrieval cutoff; its date-only schedule policy waits until 36 hours after the latest mapped date.

Pre-lock gate checks:

```bash
bash -n scripts/run_and_archive_prelock_v1.sh
DUNKEST_MAX_PRELOCK_HOURS=37 bash scripts/run_and_archive_prelock_v1.sh
bash scripts/run_and_archive_prelock_v1.sh
```

The second and third commands are expected to exit before a model or scrape run: the override exceeds the hard 36-hour maximum, and the current earliest kickoff remains outside the allowed window.

## Optimizer, collection and scoring checks

- Existing deterministic tests independently validate roster constraints, multipliers, captain/slot consistency, transfer malus, solver feasibility and reported expected totals.
- Existing controlled post-match fixtures test missing results, conflicting duplicate actuals, incomplete rosters, absent coach results, archive hash corruption, invalid timestamps, and score completeness.
- The archive writer now additionally has explicit interrupted-write tests. Realized scoring also fails closed on missing player results and missing, invalid or non-finite coach outcomes. These checks improve crash and incomplete-data behavior, but do not make any existing October snapshots retroactively valid.
- Synthetic tests verify code paths and rule arithmetic only. No synthetic result is reported as measured team performance.

## Tests and verification

Full suite:

```bash
PYTHONPATH=src .venv/bin/pytest -q -W error::DeprecationWarning
```

Latest result on the current tree: **635 passed** in 20.30 seconds. One non-failing joblib warning reported that physical CPU core count could not be parsed and it would use logical cores.

Focused archive tests before the final full run: **44 passed** across `test_artifact_manifest.py`, `test_prelock_archive.py`, `test_post_match_collection.py` and `test_post_match_evaluator.py`.

Latest focused archive, collector and evaluator results: **35 passed**, including immutable registry authentication, tamper and future-time rejection, retry preservation, input-change rejection, unique evaluation outputs and certified-run wiring. Latest focused pre-lock/post-match archive tests: **26 passed**, including registry rollback and rejection of post-prediction source times. `git diff --check` and Python compilation passed after these changes.

The focused output-stem collision regression test for the schema audit passed (**1 passed**); it verifies that an existing report is left unchanged and the audit exits before loading data.

Latest targeted coach-rule run: **9 passed**, including the new full margin-boundary check. The broader coach, plusvalenza and optimizer focused run immediately before adding that test passed **60 tests**.

The focused post-match collector and early-cutoff orchestration run passed **13 tests**, including the no-read regression and proof that early collection does not proceed to evaluation:

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/test_post_match_collection.py tests/test_prelock_archive.py::test_postmatch_pipeline_does_not_evaluate_when_collector_is_before_safe_cutoff
```

Post-match CLI smoke checks succeeded (exit code 0) without accessing archive data:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_dunkest_postmatch_oos_pipeline_v1.py --help
PYTHONPATH=src .venv/bin/python scripts/build_dunkest_post_match_results_v1.py --help
PYTHONPATH=src .venv/bin/python scripts/evaluate_archived_run_post_match_v1.py --help
```

Additional checks:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile src/dunkest/data/dunkest/official_pdk.py src/dunkest/report/artifacts.py src/dunkest/pipeline/season_opener.py src/dunkest/models/multiseason_training.py scripts/validate_dunkest_multiseason_ensemble_walk_forward_v1.py
git diff --check
```

Both completed successfully.

## Artifacts produced

- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1.md`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1.json`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1_metrics.csv`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1_predictions.csv`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v2.md`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v2.json`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v2_metrics.csv`
- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v2_predictions.csv`
- `scripts/audit_dunkest_multiseason_temporal_baselines_20261018_v1.py`
- `reports/audit/dunkest_multiseason_temporal_baselines_20261018_v1.md`
- `reports/audit/dunkest_multiseason_temporal_baselines_20261018_v1.json`
- `reports/audit/dunkest_multiseason_temporal_baselines_20261018_v1_metrics.csv`
- `scripts/audit_dunkest_training_inference_schema_20261018_v1.py`
- `reports/audit/dunkest_training_inference_schema_20261018_v1.md`
- `reports/audit/dunkest_training_inference_schema_20261018_v1.json`
- `reports/audit/dunkest_training_inference_schema_20261018_v2.md`
- `reports/audit/dunkest_training_inference_schema_20261018_v2.json`
- `tests/test_training_inference_schema_audit.py`
- `scripts/audit_dunkest_optimizer_synthetic_risk_20261018_v1.py`
- `reports/audit/dunkest_optimizer_synthetic_risk_20261018_v1.md`
- `reports/audit/dunkest_optimizer_synthetic_risk_20261018_v1.json`
- `src/dunkest/backtest/realized_scoring.py` and `tests/test_realized_scoring.py` (fail-closed handling for missing outcome inputs)
- `tests/test_rules_pdk.py` (full coach margin-bucket boundary regression for scalar and vectorized scoring)
- `src/dunkest/data/dunkest/official_pdk.py`, `src/dunkest/report/artifacts.py`, `src/dunkest/pipeline/season_opener.py`, `src/dunkest/models/multiseason_training.py`, `tests/test_artifact_manifest.py` and `tests/test_official_pdk_labels.py` (historical minute-label, official overlay, rookie-label and plusvalenza-cache provenance)
- `scripts/build_dunkest_post_match_results_v1.py` and `tests/test_post_match_collection.py` (immutable post-match source fingerprints and retry-safe audit outputs)
- `scripts/build_dunkest_post_match_results_v1.py` and `tests/test_post_match_collection.py` (safe retrieval cutoff now precedes official outcome-file access)
- `scripts/evaluate_archived_run_post_match_v1.py` and `tests/test_post_match_evaluator.py` (versioned retry-safe evaluation artifacts)
- `src/dunkest/report/artifacts.py`, `scripts/evaluate_archived_run_post_match_v1.py`, `tests/test_artifact_manifest.py` and `tests/test_post_match_evaluator.py` (schema-2 post-match manifest registry and tamper checks)
- `scripts/run_dunkest_postmatch_oos_pipeline_v1.py` and `tests/test_prelock_archive.py` (certified-archive-to-collection-to-evaluation wiring)
- `scripts/run_dunkest_postmatch_oos_pipeline_v1.py` and `tests/test_prelock_archive.py` (early-cutoff collection stops before evaluation)
- `scripts/archive_dunkest_pre_lock_run_v1.py` and `tests/test_prelock_archive.py` (pre-lock registry and failure rollback)
- `scripts/run_and_archive_prelock_v1.sh` (ambiguous new-run rejection)
- This completion report.

No prospective result, frozen manifest, or model artifact was overwritten. The schema audit V1 report regeneration described above is the one known versioned-report overwrite during this work; its original bytes are unavailable.

## Git state at report generation

The branch remains `codex/claude-audit-hardening-20261015` at HEAD `de36ce0`; nothing was committed or pushed. The working tree still contains the pre-existing user changes listed during the initial audit, plus the versioned walk-forward, baseline, training/inference schema and synthetic optimizer audits, archive atomicity changes, pre-lock run-identity guard, realized-score fail-closed fix, completion report updates, and associated tests. These changes remain uncommitted. `git diff --check` is clean.

## Remaining limitations and required data

1. The host denied process enumeration; running training/scraping process state could not be verified.
2. Standalone pre-match manifests now include code provenance, capture time, source label and content hashes, but individual source timestamps/provenance still have to be fresh and verified by the strict run archiver. Current captures fail that check.
3. The changed official-only history feature definitions pass parity and temporal tests and have now been used in chronological walk-forward validation. The measured training-window advantage is small; do not claim lineup gains from it.
4. Coach score reports mostly evaluate reconstructed base scores at neutral credits. Official coach outcomes and authentic historical coach-CR pairs remain necessary for price-adjusted calibration.
5. The optimizer's plusvalenza shadow-price floor is a conservative proxy; strategy-level and multi-week effects need prospective complete rosters and outcomes.
6. A single GW1 is descriptive. Strategy selection requires multiple complete prospective gameweeks with the same pre-lock data, frozen variants, official outcomes, transfer state and malus.

## Next actions, in priority order

1. From 2026-10-18 12:00 UTC, run `bash scripts/run_and_archive_prelock_v1.sh`; accept the result only if its independent registry and freshness review marks it `pre_lock_eligible`.
2. Freeze any strategy variants from that same input bundle before evaluating outcomes. Keep the GW1 result freeze through 2026-10-23 12:00 UTC.
3. After the latest fixture and safe retrieval cutoff, run `scripts/run_dunkest_postmatch_oos_pipeline_v1.py` on the certified archive. Require complete ten-player and coach coverage and valid official results.
4. Keep collecting immutable prospective rounds; after several complete rounds, compare the predeclared lineup policies with paired per-round metrics and report exclusions and uncertainty.
5. Revisit model or optimizer policy changes only with a new, reproducible improvement that remains stable across temporal folds and cohorts.
