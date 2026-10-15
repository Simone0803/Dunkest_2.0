# V9 past-only residual calibration audit

Created UTC: 2026-10-13T12:22:42.213326+00:00

## Protocol

For each held-out season, the affine calibrator and mean-residual offset are fitted only on earlier seasons’ saved OOF predictions and labels. The calibration is then evaluated on the next season. The first OOF season is used only as calibration training data; no 2025/26 or prospective 2026/27 holdout is read.

## Metrics

| test_season | method              | n     | mae    | rmse   | bias_pred_minus_actual | delta_mae_vs_raw | ci95_low_delta | ci95_high_delta | round_clusters |
| ----------- | ------------------- | ----- | ------ | ------ | ---------------------- | ---------------- | -------------- | --------------- | -------------- |
| 2023-24     | raw                 | 18918 | 7.4638 | 9.7477 | -0.8939                | nan              | nan            | nan             | nan            |
| 2023-24     | past_only_affine    | 18918 | 7.4876 | 9.7505 | -0.7691                | 0.0238           | 0.0208         | 0.0268          | 153.0          |
| 2023-24     | past_only_mean_bias | 18918 | 7.47   | 9.738  | -0.7815                | 0.0062           | 0.0045         | 0.0078          | 153.0          |
| 2024-25     | raw                 | 19589 | 7.4632 | 9.7616 | -0.6864                | nan              | nan            | nan             | nan            |
| 2024-25     | past_only_affine    | 19589 | 7.4689 | 9.7278 | -0.194                 | 0.0057           | -0.0022        | 0.0141          | 158.0          |
| 2024-25     | past_only_mean_bias | 19589 | 7.5006 | 9.7392 | -0.1857                | 0.0374           | 0.0299         | 0.0453          | 158.0          |

`delta_mae_vs_raw` is calibrated MAE minus raw MAE; negative favors calibration. Confidence intervals resample round clusters within each held-out season.

## Fitted coefficients

| test_season | calibration_train_seasons | n_train_oof | n_test | affine_intercept | affine_slope | mean_residual_offset | raw_train_mae | calibrated_train_mae |
| ----------- | ------------------------- | ----------- | ------ | ---------------- | ------------ | -------------------- | ------------- | -------------------- |
| 2023-24     | 2022-23                   | 19155       | 18918  | 0.3665           | 0.984        | 0.1124               | 7.433         | 7.4515               |
| 2024-25     | 2022-23;2023-24           | 38073       | 19589  | -0.0836          | 1.0378       | 0.5007               | 7.4483        | 7.474                |

## Limitations

- Only 2023/24 and 2024/25 can be evaluated because calibration needs at least one prior OOF season.
- The experiment evaluates game-level score calibration, not lineup-level utility or coach/transfer scoring.
- Two test seasons are not sufficient for production promotion; all results are exploratory.
- No 2025/26 final holdout or frozen 2026/27 GW1 predictions were read or changed.

## Artifacts

- `reports/audit/dunkest_v9_past_only_calibration_20261013_v1_metrics.csv`
- `reports/audit/dunkest_v9_past_only_calibration_20261013_v1_coefficients.csv`
- `reports/audit/dunkest_v9_past_only_calibration_20261013_v1_predictions.csv`
- `reports/audit/dunkest_v9_past_only_calibration_20261013_v1.json`
- `reports/audit/dunkest_v9_past_only_calibration_20261013_v1.md`
