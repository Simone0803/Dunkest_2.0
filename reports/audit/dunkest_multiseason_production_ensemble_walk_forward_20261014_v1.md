# Production ensemble: single-season vs multi-season walk-forward

Generated UTC: 2026-10-14T18:27:25.326370+00:00

This experiment runs the actual production ensemble and feature adapter on official Dunkest PDK labels. It does not modify production weights or configuration.

## Overall metrics

| Test season | Method | Train rows | MAE | RMSE | Bias | Ensemble weights |
|---|---|---:|---:|---:|---:|---|
| 2022-23 | previous_season_only | 18422 | 7.5750 | 9.8654 | -0.3688 | `{"gbr": 0.333710943094339, "rf": 0.33193985538894305, "ridge": 0.33434920151671793}` |
| 2022-23 | all_prior_seasons | 36084 | 7.5676 | 9.8733 | -0.5193 | `{"gbr": 0.3341485060889224, "rf": 0.331983377674156, "ridge": 0.33386811623692164}` |
| 2022-23 | all_prior_seasons_low_history_weighted | 36084 | 7.5634 | 9.8726 | -0.5473 | `{"gbr": 0.33417575921124615, "rf": 0.3320074651283845, "ridge": 0.3338167756603692}` |
| 2023-24 | previous_season_only | 19165 | 7.5922 | 9.8356 | -0.0506 | `{"gbr": 0.3344467733937777, "rf": 0.33160954163662715, "ridge": 0.33394368496959514}` |
| 2023-24 | all_prior_seasons | 55249 | 7.5573 | 9.8382 | -0.3593 | `{"gbr": 0.33452056433572563, "rf": 0.33183767077007664, "ridge": 0.33364176489419767}` |
| 2023-24 | all_prior_seasons_low_history_weighted | 55249 | 7.5571 | 9.8397 | -0.3839 | `{"gbr": 0.33448582444781744, "rf": 0.3317857628956194, "ridge": 0.33372841265656306}` |
| 2024-25 | previous_season_only | 18927 | 7.6251 | 9.9216 | -0.0628 | `{"gbr": 0.3325421722976022, "rf": 0.33305711486156453, "ridge": 0.3344007128408333}` |
| 2024-25 | all_prior_seasons | 74176 | 7.6088 | 9.9184 | -0.3275 | `{"gbr": 0.3342768007812384, "rf": 0.3321051023071861, "ridge": 0.3336180969115755}` |
| 2024-25 | all_prior_seasons_low_history_weighted | 74176 | 7.6068 | 9.9191 | -0.3511 | `{"gbr": 0.33432167431588933, "rf": 0.3320869317000964, "ridge": 0.3335913939840143}` |

## Cohort metrics

| Test season | Method | Cohort | N | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|---:|
| 2022-23 | all_prior_seasons | all | 19165 | 7.5676 | 9.8733 | -0.5193 |
| 2022-23 | all_prior_seasons | actual_ge_25 | 4310 | 12.6897 | 15.1854 | -11.8766 |
| 2022-23 | all_prior_seasons | actual_ge_30 | 2903 | 14.6786 | 17.0517 | -14.2784 |
| 2022-23 | all_prior_seasons | low_history_le_5 | 456 | 5.8314 | 7.6793 | 0.7056 |
| 2022-23 | all_prior_seasons | history_gt_5 | 18709 | 7.6099 | 9.9207 | -0.5491 |
| 2022-23 | all_prior_seasons_low_history_weighted | all | 19165 | 7.5634 | 9.8726 | -0.5473 |
| 2022-23 | all_prior_seasons_low_history_weighted | actual_ge_25 | 4310 | 12.7101 | 15.2056 | -11.9051 |
| 2022-23 | all_prior_seasons_low_history_weighted | actual_ge_30 | 2903 | 14.7005 | 17.0730 | -14.3044 |
| 2022-23 | all_prior_seasons_low_history_weighted | low_history_le_5 | 456 | 5.7944 | 7.6512 | 0.6198 |
| 2022-23 | all_prior_seasons_low_history_weighted | history_gt_5 | 18709 | 7.6065 | 9.9206 | -0.5757 |
| 2022-23 | previous_season_only | all | 19165 | 7.5750 | 9.8654 | -0.3688 |
| 2022-23 | previous_season_only | actual_ge_25 | 4310 | 12.5400 | 15.0558 | -11.6469 |
| 2022-23 | previous_season_only | actual_ge_30 | 2903 | 14.4889 | 16.8939 | -14.0290 |
| 2022-23 | previous_season_only | low_history_le_5 | 456 | 5.9229 | 7.7227 | 0.9652 |
| 2022-23 | previous_season_only | history_gt_5 | 18709 | 7.6153 | 9.9119 | -0.4013 |
| 2023-24 | all_prior_seasons | all | 18927 | 7.5573 | 9.8382 | -0.3593 |
| 2023-24 | all_prior_seasons | actual_ge_25 | 4369 | 12.4294 | 14.8560 | -11.4729 |
| 2023-24 | all_prior_seasons | actual_ge_30 | 2972 | 14.3556 | 16.6157 | -13.8627 |
| 2023-24 | all_prior_seasons | low_history_le_5 | 518 | 5.7430 | 7.5935 | 0.9712 |
| 2023-24 | all_prior_seasons | history_gt_5 | 18409 | 7.6084 | 9.8940 | -0.3967 |
| 2023-24 | all_prior_seasons_low_history_weighted | all | 18927 | 7.5571 | 9.8397 | -0.3839 |
| 2023-24 | all_prior_seasons_low_history_weighted | actual_ge_25 | 4369 | 12.4521 | 14.8768 | -11.5074 |
| 2023-24 | all_prior_seasons_low_history_weighted | actual_ge_30 | 2972 | 14.3848 | 16.6391 | -13.8989 |
| 2023-24 | all_prior_seasons_low_history_weighted | low_history_le_5 | 518 | 5.7144 | 7.5634 | 0.8993 |
| 2023-24 | all_prior_seasons_low_history_weighted | history_gt_5 | 18409 | 7.6090 | 9.8962 | -0.4200 |
| 2023-24 | previous_season_only | all | 18927 | 7.5922 | 9.8356 | -0.0506 |
| 2023-24 | previous_season_only | actual_ge_25 | 4369 | 12.1565 | 14.5849 | -11.1093 |
| 2023-24 | previous_season_only | actual_ge_30 | 2972 | 14.0535 | 16.3143 | -13.4859 |
| 2023-24 | previous_season_only | low_history_le_5 | 518 | 6.0523 | 7.8357 | 1.6394 |
| 2023-24 | previous_season_only | history_gt_5 | 18409 | 7.6355 | 9.8860 | -0.0981 |
| 2024-25 | all_prior_seasons | all | 19590 | 7.6088 | 9.9184 | -0.3275 |
| 2024-25 | all_prior_seasons | actual_ge_25 | 4425 | 12.3269 | 14.9203 | -11.4045 |
| 2024-25 | all_prior_seasons | actual_ge_30 | 2919 | 14.4856 | 16.9488 | -13.9881 |
| 2024-25 | all_prior_seasons | low_history_le_5 | 480 | 5.4686 | 7.2078 | 1.1357 |
| 2024-25 | all_prior_seasons | history_gt_5 | 19110 | 7.6626 | 9.9770 | -0.3643 |
| 2024-25 | all_prior_seasons_low_history_weighted | all | 19590 | 7.6068 | 9.9191 | -0.3511 |
| 2024-25 | all_prior_seasons_low_history_weighted | actual_ge_25 | 4425 | 12.3456 | 14.9381 | -11.4357 |
| 2024-25 | all_prior_seasons_low_history_weighted | actual_ge_30 | 2919 | 14.5106 | 16.9689 | -14.0219 |
| 2024-25 | all_prior_seasons_low_history_weighted | low_history_le_5 | 480 | 5.4243 | 7.1571 | 1.0668 |
| 2024-25 | all_prior_seasons_low_history_weighted | history_gt_5 | 19110 | 7.6616 | 9.9787 | -0.3867 |
| 2024-25 | previous_season_only | all | 19590 | 7.6251 | 9.9216 | -0.0628 |
| 2024-25 | previous_season_only | actual_ge_25 | 4425 | 12.0566 | 14.6611 | -11.0011 |
| 2024-25 | previous_season_only | actual_ge_30 | 2919 | 14.1753 | 16.6520 | -13.5692 |
| 2024-25 | previous_season_only | low_history_le_5 | 480 | 5.5169 | 7.2941 | 1.1987 |
| 2024-25 | previous_season_only | history_gt_5 | 19110 | 7.6780 | 9.9787 | -0.0945 |

## Limitations and decision

- 2025/26 is excluded because it has already been inspected by prior experiments; these folds are validation evidence, not a pristine final holdout.
- This tests player-game forecasts, not full lineup strategy performance.
- Low-history means at most five prior Dunkest rows, not a verified draft-rookie label.
- No production model/configuration or frozen 2026/27 GW1 artifact was modified.
- Promotion requires stable gains across folds and cohorts plus independent lineup-level evidence.

## Artifacts

- Metrics: `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261014_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261014_v1_predictions.csv`
