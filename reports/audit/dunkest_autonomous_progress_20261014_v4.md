# Dunkest autonomous improvement status — 2026-10-14 V4

## Summary

One bounded production improvement was completed in this pass: forecast-score-band residual quantiles now calibrate P10/P50/P90 in the opening-round multi-season predictor. All 381 tests pass. Model weights, lineup objective, risk penalty, coach probability calibration, and doubtful-player eligibility policy were not changed where evidence did not justify promotion.

## 1. Historical actuals and pre-lock snapshots

- `scripts/run_and_archive_prelock_v1.sh` remains the prospective collection entry point. It validates kickoff timing and fails closed when snapshots are stale or incomplete.
- Historical pre-lock player market, CR, injuries/availability, coach prices, transfer carry-over, and complete fixture-linked outcomes remain unavailable for the relevant archived seasons.
- Existing lineup proxy backtests remain exploratory because their candidate universe and availability/credit assumptions cannot be verified. No lineup strategy is certified superior.
- Keep 2026/27 GW1 frozen until 2026-10-23 12:00 UTC. The first mapped fixture is currently 2026-10-20 00:00 UTC; revalidate fixture mapping before the capture window.

## 2. Multi-season primary training

- Opening-round training uses certified official Dunkest PDK targets from 2020/21–2024/25 through `adapt_certified_training_rows`; 2018/19–2019/20 remain NBA history only because their Dunkest labels are not certified.
- The actual multi-season training-path smoke test trained on 93,766 rows and generated 38,517 cross-fitted calibration predictions.
- Chronological production-adapter comparison (2022/23–2024/25): all-prior-season MAE improved over previous-season-only in each fold (7.5750→7.5676; 7.5922→7.5573; 7.6251→7.6088). RMSE does not improve in every fold and bias becomes more negative.
- Extra weighting of low-history rows changes pooled MAE only slightly and can worsen high-score errors. Keep the current capped weights (1.25 for ≤5 prior rows; 1.10 for ≤10) rather than increasing them without stronger evidence.
- 2025/26 has already been inspected in prior experiments and is not a pristine final holdout.

## 3. Minutes and availability

- Historical minutes × rate decomposition does not beat the direct model consistently on MAE, RMSE, bias, and high-score cohorts. It remains a diagnostic component rather than a replacement for the direct score forecast.
- Current availability probabilities are used in expected PDK and the score-distribution mixture. The optimizer continues to exclude players with `p_play < 1.0`; the conservative policy has not been changed because trustworthy historical pre-lock questionable/GTD labels are missing for an outcome-based ablation.
- Hard OUT/inactive players remain ineligible. Do not relax eligibility solely on synthetic or post-hoc status labels.

## 4. High scores and uncertainty

- The conditional-threshold research model is promising for PDK ≥25/30, but its calibration and integration have not been validated on the exact production feature adapter sufficiently to replace the production point model.
- Added `_fit_residual_quantiles_by_prediction_band` and `_residual_quantiles_for_predictions` to `src/dunkest/models/predictor.py`.
- Quantiles are learned from strictly cross-fitted target-minus-prediction residuals, grouped by forecast score bands `<5`, `5–10`, `10–15`, `15–20`, `20–25`, `25+`, with shrinkage to pooled quantiles `n/(n+1000)`.
- `add_uncertainty_columns` now supports row-specific empirical quantiles, preserving P10≤P50≤P90 and the existing play-probability mixture.
- Independent past-only audit (2023/24 and 2024/25): score-band residual intervals increased central 80% coverage from 80.06% to 80.83% and from 80.07% to 80.75%, while mean width fell from 24.458 to 24.303 and 24.413 to 24.261 PDK, respectively. This supports interval calibration, not risk-adjusted lineup superiority.
- Full correction of score-band median residuals improves MAE but worsens RMSE and strongly increases negative mean bias; do not apply that correction to the point forecast.

## 5. Coaches and full-lineup scoring

- The coach base-score model beats previous-5/previous-10 score baselines across tested seasons, but exact historical credit-adjusted Dunkest coach outcomes still require archived coach CR and historically valid rules.
- The roster-strength adjustment and Platt-calibrated win probability worsen Brier and log loss on validation; they remain disabled/not promoted.
- The full realized lineup chain (player PDK, coach multiplier, captain multiplier, transfer malus and plusvalenza) still requires immutable pre-lock inputs and official linked outcomes. No winner claims from proxy lineups.

## Verification

- Full suite: **381 passed** with `-W error::DeprecationWarning`.
- Python compilation for modified modules and research scripts passed.
- `git diff --check` passed.
- No commit or push performed.

## Main artifacts

- `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261014_v1.md`
- `reports/audit/dunkest_score_band_interval_calibration_20261014_v1.md`
- `reports/audit/dunkest_score_band_calibration_strength_20261014_v1.md`
- `reports/audit/dunkest_score_band_calibration_implementation_20261014_v1.md`
- `scripts/run_and_archive_prelock_v1.sh`
