# Production ensemble + small Torch MLP walk-forward

Generated UTC: 2026-10-16T08:36:15.464986+00:00

## Protocol

Same certified production adapter and three past-only folds. The best standalone neural candidate from the 51-model grid was added as a fourth component; production ensemble weights are re-learned from past-only OOF predictions. No 2025/26 holdout or 2026/27 prospective outcome was used.

## Pooled comparison

                          model     n     mae    rmse     bias  mae_ge25  mae_ge30
    current production ensemble 57682 7.55239 9.82091 -0.14472  12.21193  14.19673
production ensemble + Torch MLP 57682 7.54563 9.80337 -0.05204  12.08421  14.02689

## Fold metrics

fold_season     n      mae     rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5  train_rows  test_rows  fit_seconds                                                                                                         model_weights  torch_mlp_epochs
    2022-23 19165 7.555699 9.804122               -0.095875        12.279693           4310        14.182087           2903         5.387379            384       36084      19165         88.2 {"gbr": 0.2490024373426645, "rf": 0.24884651961575388, "ridge": 0.2511657487686122, "torch_mlp": 0.25098529427296945}                 4
    2023-24 18927 7.535201 9.770346               -0.051494        12.144784           4369        14.027696           2972         5.426062            434       55249      18927        137.5  {"gbr": 0.2501899021504522, "rf": 0.2493009845614378, "ridge": 0.25015057959028675, "torch_mlp": 0.2503585336978233}                 8
    2024-25 19590 7.545867 9.834449               -0.009697        11.833997           4425        13.871720           2919         4.717241            404       74176      19590        186.8  {"gbr": 0.249830202829397, "rf": 0.24926803525660862, "ridge": 0.2502334148405681, "torch_mlp": 0.25066834707342645}                 5

## Decision

The candidate is not automatically promoted. It should replace the production ensemble only if the gains are material, stable by season, and not purchased with worse tail error or bias.

## One-shot final holdout (2025/26)

This season was not used for tuning. Current production: MAE=7.55443, RMSE=9.82487, bias=-0.11366, MAE >=25=12.02673, MAE >=30=14.09512.

Production + MLP: MAE=7.54025, RMSE=9.81298, bias=-0.14050, MAE >=25=12.03766, MAE >=30=14.08389.

Decision: not promoted. Although aggregate MAE/RMSE and the >=30 cohort improve, the >=25 cohort worsens slightly and the bias becomes more negative. This mixed result fails the predeclared promotion rule; the production ensemble remains unchanged. The 2026/27 prospective test was not used.
