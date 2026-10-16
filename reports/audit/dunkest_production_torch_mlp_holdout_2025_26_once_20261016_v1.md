# One-shot 2025/26 holdout validation: production ensemble vs production + Torch MLP

Generated UTC: 2026-10-16T08:43:35.379878+00:00

## Protocol

The 51-configuration search and 3-fold development comparison selected the small Torch MLP before this final test. The 2025/26 season was used exactly once here, only as a final evaluation; it was not used for tuning. The prospective 2026/27 GW1 remains untouched.

## Results

                             model     n     mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
       current_production_ensemble 18412 7.55443 9.82487                -0.11366         12.02673           4168         14.09512           2712          5.17052            440
production_ensemble_plus_torch_mlp 18412 7.54025 9.81298                -0.14050         12.03766           4168         14.08389           2712          5.12892            440

## Decision

Predeclared rule passed: **False**. No model code was modified by this evaluation.
