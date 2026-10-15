# Dunkest prediction calibration workstreams — 2026-10-15

## Scope and safeguards

This work targets the reliability of individual-player forecasts and coach/plusvalenza predictions used for the current season. It is not a historical full-lineup validation. No synthetic historical CR, injury, coach-market or plusvalenza values were created. The frozen 2026/27 GW1 prospective bundle was not loaded or used for tuning.

## 1. Plusvalenze

### Data integrity

- Fixed official-season discovery: a season is accepted only when the first-week response has at least 28 distinct NBA team codes. This avoids accepting unrelated/partial Dunkest seasons that happen to include one or two NBA team codes.
- Moved the cache to versioned v4 paths, preserving the old v3 cache.
- Rebuilt history from the official endpoint: 93,744 rows across five verified NBA seasons (2020/21–2024/25), each with 30 distinct team codes. Observed gameweek counts are retained as returned by the official source; missing rows are not filled synthetically.

### Point forecast and probability calibration

- ΔCR point forecast: 87,626 training rows; 17,256 past-only walk-forward validation rows.
- MAE: 0.069512 CR versus 0.182975 CR for the training-window-mean baseline.
- Added regularized multinomial calibration for gain/flat/loss probabilities, trained only on prior out-of-fold conversion probabilities. The current row is never used to calibrate its own probability.
- Sequential evaluation after calibration burn-in (15,451 rows): mean gain-probability bias fell from +3.687 to +0.205 percentage points; multiclass Brier improved from 0.318655 to 0.314660 and log loss from 0.644684 to 0.562063.
- The one-CR-plus probability remains explicitly uncalibrated.

**Limit:** this probability calibration conditions on the observed official PDK score. It calibrates the CR-conversion component; it does not certify the full end-to-end probability when PDK itself is uncertain. Historical pre-lock PDK forecast snapshots are not available, so none were reconstructed.

Report: reports/audit/dunkest_plusvalenza_calibration_20261015_v1.md

## 2. Coach forecasts

- Re-evaluated Monte Carlo base-coach-score forecasts on earlier training seasons (2022/23 and 2023/24), validation season 2024/25, and a later audit season 2025/26.
- On 2024/25, raw expected-score MAE was 15.0584 with bias +0.0814; on 2025/26, MAE was 15.0636 with bias +0.1377.
- A past-only global bias correction reduced MAE by only about 0.0011–0.0012 coach points; paired game-cluster 95% intervals crossed zero. Affine and score-band corrections worsened MAE in both seasons, so no point-score correction was promoted.
- The simulated P10–P90 interval covered 84.68% of outcomes against a nominal 80%, so it is slightly conservative. No narrowing was promoted without a stable out-of-sample gain.
- The score audit uses base coach PDK at CR=10 for both teams, isolating the Monte Carlo team-score component from the deterministic CR multiplier.

Report: reports/audit/dunkest_coach_score_calibration_20261015_v1.md

## 3. Player-level production validation

- Expanded diagnostics on the exact production trainer's chronological player-level walk-forward predictions, including official draft-class rookies, low-history players, team changes, and predicted-score bands.
- The active uncorrected production baseline covers 57,682 individual player-game predictions over 2022/23–2024/25: MAE 7.5573, RMSE 9.8230, bias −0.1067 PDK. The previous-10-games baseline has MAE 7.7756 and RMSE 10.1316. This compares individual-player forecasts, not historical fantasy lineups.
- Tested a shrinkage correction for the team-change cohort using only out-of-fold residuals. In paired outer-fold evaluation, overall MAE moved by less than 0.0002 PDK, while the team-change cohort improved in 2023/24 but worsened in 2022/23 and 2024/25. The effect is not stable, so **the correction was not promoted** and the active predictor remains uncorrected.
- The cohort breakdown is retained as a diagnostic for future monitoring, not as a reason to change weights without stronger evidence.

Reports:
- Baseline production walk-forward: reports/audit/dunkest_production_trainer_walk_forward_20261014_v1.md
- Cohort diagnostics: reports/audit/dunkest_production_player_cohort_calibration_20261015_v1.md
- Candidate-correction experiment and decision: reports/audit/dunkest_team_change_bias_correction_20261015_v1.md
- Experimental corrected run (not active production): reports/audit/dunkest_production_trainer_walk_forward_20261015_v3.md

## Verification

- Full test suite: **411 passed**.
- compileall: passed for modified Python modules and audit scripts.
- git diff --check: passed.
- No files staged; no commit or push; no destructive cleanup.
- The current-season GW1 prospective bundle remains frozen and was not used.
