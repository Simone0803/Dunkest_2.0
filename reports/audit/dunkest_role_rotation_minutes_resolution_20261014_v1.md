# Role/rotation and minutes integration — verification 2026-10-14

## Scope
Autonomous verification of the two requested workstreams: cohort-aware feature impact and a more robust expected-minutes model. Existing user changes were preserved. No holdout or prospective 2026/27 GW1 outcomes were used for tuning.

## Workstream A — role changes, rotation, and history cohorts
The production feature pipeline already includes past-only team-transition/tenure and minute-volatility signals. The current cohort audit is `dunkest_role_rotation_cohort_audit_20261014_v3.md`, with outer folds for 2022/23–2024/25.

HGB player-game MAE by cohort (adapter -> expanded lags -> rotation-aware):
- All: 7.5743 -> 7.5615 -> 7.5637.
- Rookie/debut-season proxy: 6.4827 -> 6.3988 -> 6.3916.
- Low-history non-rookies: 5.0367 -> 4.8764 -> 4.8877.
- Experienced team changes: 6.9327 -> 7.0260 -> 6.8991.
- Stable veterans: expanded lags do not improve the adapter baseline consistently.

Interpretation: expanded lag features help debut-season and low-history cohorts. Rotation-aware features recover much of the expanded-lag degradation for team-change players, but gains are not uniform enough to justify a hard-coded specialist blend. Keep the features available to the learned ensemble; do not hard-code cohort weights. Team-change labels remain archive-derived proxies, not certified transaction events.

## Workstream B — expected minutes
The expected-minutes HGB model is trained with past-only inputs and exports `expected_min_model_shadow`; it does not replace `expected_min`, enter the PDK ensemble weights, or rescale `expected_pdk`.

Nested walk-forward metrics from `dunkest_minutes_hybrid_nested_20261014_v1.md`:
- Previous-five baseline: minutes MAE 5.1269, RMSE 6.7808.
- HGB minutes model: MAE 4.9839, RMSE 6.4530.
- Nested gated hybrid: MAE 4.9758, RMSE 6.4619.
- HGB underperforms the previous-five baseline on low-history players (5.6774 vs 5.4906 MAE); nested gating improves that subgroup to 5.6327 but is not a robust all-segment win.
- Applying the minutes estimate to adjust PDK predictions degrades overall PDK MAE even at 10% scaling (7.5721 -> 7.5816); full scaling degrades it to 7.7646.

Decision: the minutes model is integrated and visible for diagnostics, but not allowed to alter fantasy-score predictions or optimizer decisions until a nested, cohort-consistent downstream PDK improvement is demonstrated. This is the evidence-based resolution; forcing the new minutes forecast into PDK would make the model worse on current out-of-sample evidence.

## Verification performed
- Full test suite: **399 passed in 9.24s**, with deprecation warnings treated as errors.
- Focused tests for player features, role/minutes projection, and multi-season training: **33 passed**.
- The test command must include `PYTHONPATH=src` in this checkout because the local `.venv` Python does not automatically expose the editable source package: `PYTHONPATH=src ./.venv/bin/python -m pytest -q -W error::DeprecationWarning`.
- A first test invocation without `PYTHONPATH=src` failed during collection with `ModuleNotFoundError: dunkest`; this was an invocation/environment-path issue, not a failing regression. The corrected full run passed.
- No model weights were manually changed. No commit or push was performed.
