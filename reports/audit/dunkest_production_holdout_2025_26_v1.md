# Production PDK trainer — 2025/26 retrospective holdout audit

Generated UTC: 2026-10-18T13:59:38.653745+00:00

## Scope and leakage controls

- Train: official PDK rows from 2020-21, 2021-22, 2022-23, 2023-24, 2024-25 (93,766 rows).
- Test: 18,412 matched official-label player-games from 2025/26.
- Chronology: last training date 2025-04-11, first test date 2025-10-21.
- Exact production `train_models` and certified multi-season feature adapter; no hyperparameter or blend selection on 2025/26.
- This season was inspected by earlier experiments; treat this as robustness evidence, not a pristine holdout.
- No 2026/27 prospective inputs loaded; no production code/config changed.

## Overall results

| Method | N | MAE | RMSE | Bias pred−actual | MAE actual ≥25 | MAE actual ≥30 |
|---|---:|---:|---:|---:|---:|---:|
| production_ensemble | 18,412 | 7.5149 | 9.7659 | -0.0126 | 11.7999 | 13.7916 |
| previous10_baseline | 18,412 | 7.7886 | 10.1539 | -0.0479 | 11.9017 | 13.7713 |

## Paired date-cluster uncertainty

Delta MAE (production minus prev10): -0.27375; 95% CI [-0.31653, -0.23365] over 160 game dates. Negative favors production.

## Cohort results

          cohort              method     n     mae    rmse  bias_pred_minus_actual  n_actual_ge_25  mae_actual_ge_25  bias_actual_ge_25  n_actual_ge_30  mae_actual_ge_30  bias_actual_ge_30
             all production_ensemble 18412  7.5149  9.7659                 -0.0126            4168           11.7999           -10.8962            2712           13.7916           -13.3412
             all previous10_baseline 18412  7.7886 10.1539                 -0.0479            4168           11.9017           -10.5639            2712           13.7713           -12.9438
    actual_ge_25 production_ensemble  4168 11.7999 14.3488                -10.8962            4168           11.7999           -10.8962            2712           13.7916           -13.3412
    actual_ge_25 previous10_baseline  4168 11.9017 14.5813                -10.5639            4168           11.9017           -10.5639            2712           13.7713           -12.9438
    actual_ge_30 production_ensemble  2712 13.7916 16.3103                -13.3412            2712           13.7916           -13.3412            2712           13.7916           -13.3412
    actual_ge_30 previous10_baseline  2712 13.7713 16.4634                -12.9438            2712           13.7713           -12.9438            2712           13.7713           -12.9438
low_history_le_5 production_ensemble   524  5.2123  7.1371                  0.2675              24           17.0011           -16.7828              10           24.2213           -24.2213
low_history_le_5 previous10_baseline   524  6.1256  8.2934                  0.6151              24           17.0335           -15.9700              10           23.8686           -23.8686
    history_gt_5 production_ensemble 17888  7.5823  9.8323                 -0.0208            4144           11.7698           -10.8622            2702           13.7530           -13.3010
    history_gt_5 previous10_baseline 17888  7.8373 10.2033                 -0.0673            4144           11.8719           -10.5326            2702           13.7340           -12.9033
prediction_ge_25 production_ensemble  2977  9.9949 12.5985                  0.3546            1897            8.5571            -6.5717            1488            9.9296            -9.1088
prediction_ge_25 previous10_baseline  2977 10.2828 12.9627                  1.0101            1897            8.7185            -5.8099            1488            9.8307            -8.3224
prediction_ge_30 production_ensemble  1485 10.5286 13.3783                  0.5745            1076            8.4545            -5.2833             888            9.0109            -7.6354
prediction_ge_30 previous10_baseline  1485 10.8080 13.7470                  1.5821            1076            8.5880            -4.1447             888            8.9383            -6.4734

## Decision

This audit checks whether the current production trainer generalizes to the 2025/26 official-label subset and where errors remain concentrated. It does not certify lineup quality because authentic pre-lock market/injury/coach snapshots are not complete for the historical season. Do not use this single season to tune or promote a challenger; use it to guide future diagnostics, then require repeated temporal folds and lineup-level evidence.

## Artifacts

- `reports/audit/dunkest_production_holdout_2025_26_v1.json`
- `reports/audit/dunkest_production_holdout_2025_26_v1.md`
- `reports/audit/dunkest_production_holdout_2025_26_v1_metrics.csv`
- `reports/audit/dunkest_production_holdout_2025_26_v1_predictions.csv`
- `reports/audit/dunkest_production_holdout_2025_26_v1_cohorts.csv`
