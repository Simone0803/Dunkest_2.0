# Production PDK history-source ablation

Generated UTC: 2026-10-13T10:07:21.127376+00:00

## Protocol

- Same 2025/26 player/team logs and verified official PDK target labels in both arms.
- Proxy arm uses the current production PDK history column as-is.
- Challenger replaces the PDK history column with verified official PDK wherever available, retaining proxy values only where the overlay is missing.
- Both arms use the unchanged production feature builder and trainer, including chronological OOF folds and fold-local model weighting.
- No production code/configuration was changed.

## Results

                                mode  n_oof      mae     rmse  bias_pred_minus_actual  actual_mean  predicted_mean  within_3_pdk_pct  within_5_pdk_pct                                                               selected_model_weights                                                                                projection_weights  official_target_rows_in_matrix
                       proxy_history   7407 7.552930 9.838438               -0.185167    16.073945       15.888778         25.826920         42.257324   {"gbr": 0.3331292739151731, "rf": 0.33315720410494887, "ridge": 0.333713521979878}                    {"ensemble": 0.8681170814706702, "minutes": 0.0, "prior": 0.13188291852932976}                           18412
official_history_with_proxy_fallback   7407 7.546927 9.831048               -0.201490    16.073945       15.872455         25.853922         42.540840 {"gbr": 0.33351455913377437, "rf": 0.3331197342545641, "ridge": 0.33336570661166154} {"ensemble": 0.8629595492937259, "minutes": 1.4408721704215776e-18, "prior": 0.13704045070627408}                           18412

## Paired date-cluster bootstrap

- Paired predictions: 7,407 over 64 game dates.
- Delta MAE (official-history minus proxy-history): -0.0060.
- 95% interval: [-0.0140, 0.0019].
- Bootstrap fraction favoring official history: 0.9314.

## Decision rule

Treat this as an ablation on a previously examined season, not as a final independent holdout. Only consider a production change if official-history features consistently improve the expanding-origin folds and the inference path is covered by tests. Do not tune on the frozen 2026/27 GW1 prospective holdout.

## Limitations

- This is a temporal OOF ablation within 2025/26, not a new untouched season holdout; that season has already been inspected by other experiments.
- The OOF output follows the current production trainer's expanding date folds and fold-local ensemble weighting. It does not validate full lineup scores.
- Official PDK overlays may be incomplete; proxy values are used only as history fallback when an official label is absent.
