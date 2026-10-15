# Sequential blend-weight validation — V1

Generated UTC: 2026-10-13T14:15:50.353230+00:00

## Protocol

Choose the blend weight among 25%, 50%, and 75% mixture on 2022/23 MAE only, freeze it, and evaluate the exact rule on 2023/24 and 2024/25. No 2025/26 holdout or 2026/27 prospective snapshot is loaded. The later folds have been inspected in prior exploratory work, so this is stronger temporal validation but not a pristine final test.

Selected weight: **75% mixture**. Selection-fold MAE: `{0.25: 7.566101791511507, 0.5: 7.556659807639372, 0.75: 7.554389247699377}`.

## Results

                             scope             candidate     n     mae    rmse     bias  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30
                           2022-23            direct_hgb 19165 7.58273 9.82520  0.07992         12.07991           4310         13.86554           2903
                           2022-23 blend_mix_weight_0.75 19165 7.55439 9.80484  0.00498         12.06006           4310         13.84301           2903
                           2023-24            direct_hgb 18927 7.56311 9.79798  0.03394         12.06123           4369         13.87107           2972
                           2023-24 blend_mix_weight_0.75 18927 7.55718 9.79491 -0.00604         12.08033           4369         13.96568           2972
                           2024-25            direct_hgb 19590 7.57088 9.86730 -0.04583         11.94283           4425         13.99184           2919
                           2024-25 blend_mix_weight_0.75 19590 7.56076 9.85639 -0.09413         11.94128           4425         14.03556           2919
pooled_later_folds_2023-24_2024-25            direct_hgb 38517 7.56706 9.83330 -0.00663         12.00166           8794         13.93091           5891
pooled_later_folds_2023-24_2024-25 blend_mix_weight_0.75 38517 7.55900 9.82623 -0.05084         12.01036           8794         14.00030           5891

## Paired date-cluster bootstrap on later folds

Delta MAE = frozen blend minus direct HGB; negative favors the blend.

{
  "overall": {
    "n": 38517,
    "clusters": 312,
    "delta_mae_candidate_minus_direct": -0.00806072415768957,
    "ci95": [
      -0.015192301667440004,
      -0.0007782996266966155
    ],
    "reps": 5000
  },
  "actual_ge25": {
    "n": 8794,
    "clusters": 312,
    "delta_mae_candidate_minus_direct": 0.008706586673019491,
    "ci95": [
      -0.012432567656073128,
      0.029475485116872185
    ],
    "reps": 5000
  },
  "actual_ge30": {
    "n": 5891,
    "clusters": 312,
    "delta_mae_candidate_minus_direct": 0.06939080622054468,
    "ci95": [
      0.040732285361681754,
      0.09799086937921538
    ],
    "reps": 5000
  }
}

## Decision

This validates or rejects the weight-selection rule, not lineup-level utility. Do not promote until the complete historical lineup replay demonstrates an improvement under the same candidate pool, credits, coaches, and transfer rules.

No production change, no commit/push.
