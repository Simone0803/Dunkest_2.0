# Paired refinement MLP vs current production ensemble

Generated UTC: 2026-10-18T12:16:26.195670+00:00

Paired predictions: 57,682; folds: 2022/23–2024/25; no 2025/26 or 2026/27 outcomes used.

## Per-season comparison

 season     n  production_mae  mlp_mae  delta_mae_mlp_minus_production  production_rmse  mlp_rmse  production_bias  mlp_bias  mae_actual_ge25_mlp  mae_actual_ge25_prod  mae_actual_ge30_mlp  mae_actual_ge30_prod
2022-23 19165         7.51931  7.51505                        -0.00427          9.75375   9.78997         -0.04224  -0.34570             12.34728              12.13164             14.23584              13.99738
2023-24 18927         7.49846  7.50315                         0.00469          9.74624   9.75286         -0.17955  -0.11869             12.03389              12.18094             13.79292              14.05632
2024-25 19590         7.51830  7.48893                        -0.02937          9.79320   9.82327         -0.11372  -0.47143             12.16145              11.94799             14.26131              14.02407

Equal-season macro ΔMAE (MLP − production): -0.00965.

95% game-date-cluster bootstrap interval: [-0.02158, 0.00237].

Negative ΔMAE favors the MLP. Promotion requires consistent RMSE/tail behavior and lineup-level evidence; production is unchanged.
