# Dunkest project follow-up (v7)

Generated: 2026-10-12

## Work completed

### 1. Walk-forward ensemble weight selection
Added `scripts/tune_dunkest_ensemble_weights_walk_forward_v1.py` and ran it on saved expanding-window out-of-fold predictions.

- Weight selection used only 2022/23–2024/25.
- Objective: pooled MAE; convex grid increments of 0.05.
- Selected weights: Random Forest 0.60, Ridge 0.35, previous-10 PDK mean 0.05.
- Validation MAE: 7.5658 over 57,682 player-game rows.
- Final 2025/26 descriptive holdout MAE: 7.5568, RMSE 9.8306, bias −0.0885 over 18,412 rows.
- On the same 2025/26 holdout, Random Forest MAE is 7.5775. The ensemble improvement is only 0.0207 PDK (about 0.27%) over Random Forest.
- This is an offline experimental result. No production weights or configuration were changed.

Artifacts:
- `reports/audit/dunkest_ensemble_weights_walk_forward_20261012T172631Z.md`
- Matching CSV and JSON files in `reports/audit/`

### 2. Error and calibration audit
Added `scripts/audit_dunkest_pdk_calibration_error_v1.py`. The audit uses saved walk-forward predictions and does not fit models.

Final holdout 2025/26:
- Random Forest: MAE 7.5775; RMSE 9.8563; bias −0.1725.
- Ridge: MAE 7.5887; RMSE 9.8604; bias +0.0495.
- Previous-10 mean: MAE 7.7886; RMSE 10.1539; bias −0.0479.
- 60/35/5 ensemble: MAE 7.5568; RMSE 9.8306; bias −0.0885.
- Ensemble predictions are within 3 PDK of the target in 25.96% of rows and within 5 PDK in 42.65%.

The post-hoc realized-score bands show the expected regression-to-the-mean pattern: predictions overestimate very low realized scores and underestimate the highest realized scores. Those bands are diagnostic only and cannot be used as pre-game features.

Artifacts:
- `reports/audit/dunkest_pdk_calibration_error_audit_20261012T172805Z.md`
- Matching CSV and JSON files in `reports/audit/`

### 3. Score calibration experiment
Added `scripts/evaluate_dunkest_pdk_score_calibration_v1.py`. Linear and isotonic mappings were fitted only on 2022/23–2024/25 out-of-fold predictions and evaluated on 2025/26.

| Method | MAE | RMSE |
|---|---:|---:|
| Random Forest raw | 7.5775 | 9.8563 |
| Random Forest linear calibration | 7.5747 | 9.8584 |
| Ensemble raw | 7.5568 | 9.8306 |
| Ensemble linear calibration | 7.5497 | 9.8331 |
| Ensemble isotonic calibration | 7.5544 | 9.8393 |

Calibration changes are marginal and trade a small MAE improvement for slightly worse RMSE. Neither calibrator is integrated into production.

Artifacts:
- `reports/audit/dunkest_pdk_score_calibration_20261012T172819Z.md`
- Matching CSV and JSON files in `reports/audit/`

## Verification

- All three new scripts pass Python compilation.
- Ensemble selection script completed successfully.
- Calibration/error audit scripts completed successfully.
- Full repository test suite: 222 passed, 0 failed.
- `git diff --check` passed.
- Existing local modifications and untracked artifacts were preserved; no commit, reset, or revert was performed.
- No production config or model blend was changed by this work.

## Interpretation

The new ensemble is slightly better than Random Forest on the held-out game-level PDK metric, but the gain is too small to justify production replacement without a paired comparison on the actual production task. Simple score calibration also produces only marginal improvements. Game-level PDK error is not equivalent to fantasy-lineup performance.

## Next priorities

1. Build a verified, fixture-linked walk-forward evaluation of complete Dunkest lineups: player scores, coach score, credits, injuries/availability, lineup constraints, and transfer malus.
2. Compare the current production pipeline against the candidate ensemble on exactly the same pre-game snapshots and realized outcomes; report paired MAE/RMSE, realized lineup score, regret versus an oracle lineup, and coach contribution separately.
3. Resolve historical archive provenance before using weekly-round stats as official game-level targets. Keep the two confirmed contaminated season-5 files quarantined from any clean training derivative; never overwrite raw source data.
4. Keep rookie college minutes influence capped conservatively until historical participation outcomes and pre-game role snapshots are reliable.
5. Do not tune on 2025/26 results again; retain it as the reported holdout and use later genuinely unseen data for future confirmation.
