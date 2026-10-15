# Dunkest PDK predictor search — train-only V1

Generated UTC: 2026-10-13T13:44:12.276134+00:00

## Objective

Improve player-game PDK prediction with expanding-origin validation through 2024/25. Season 2025/26 was filtered out before fitting/scoring and was not used for model selection.

## Leakage / data checks

- Training rows loaded: 93,766 across 2020/21–2024/25.
- Lag-1 PDK integrity mismatches: 0.
- Validation folds: 2022/23, 2023/24, 2024/25; each fold trains only on earlier target seasons.
- 2025/26 holdout was not loaded into this experiment.
- Metrics are player-game level; no claim of lineup-level improvement is made.

## Candidate summary

      feature_family         model  weighted_mae  weighted_rmse  weighted_bias   folds
history_flags_trends     et_leaf12       7.56075        9.83512       -0.18563 3.00000
                base     et_leaf12       7.56323        9.84024       -0.22073 3.00000
history_flags_trends      et_leaf8       7.56975        9.83910       -0.15292 3.00000
                base      et_leaf8       7.56989        9.84343       -0.19011 3.00000
history_flags_trends hist_gradient       7.57351        9.84060       -0.03775 3.00000
                base hist_gradient       7.58171        9.84347       -0.00641 3.00000

## Paired date-cluster bootstrap

- Best by pooled validation MAE: **history_flags_trends/et_leaf12** (weighted MAE 7.56075).
- Paired comparator: **base/et_leaf12** (MAE 7.56323); selected candidate paired MAE 7.56075.
- Paired rows: 57,682; date clusters: 475; bootstrap replicates: 4,000.
- MAE difference (candidate minus comparator): -0.00247; 95% date-cluster bootstrap interval [-0.00678, +0.00182].
- This interval is descriptive because the winner was selected using the same validation folds; it is not an independent confirmatory test.

## Baseline

- Previous-10 PDK mean baseline: weighted MAE 7.77555 over 57,682 fold rows.

## Interpretation

No production change is warranted from a small player-game metric change alone. Any candidate must be validated in the production inference path and must improve lineup-level outcomes before promotion.

## Artifacts

- Metrics: `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1_predictions.csv`
- Audit: `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1.json`
