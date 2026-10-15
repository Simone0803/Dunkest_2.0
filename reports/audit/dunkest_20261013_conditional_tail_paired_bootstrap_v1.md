# Conditional tail model paired bootstrap — V1

Generated UTC: 2026-10-13T14:06:39.691087+00:00

Delta MAE is mixture-threshold-25 minus the direct model; negative favors the mixture. Bootstrap resamples complete target dates within each season (3,000 repetitions). This is a paired comparison of identical player-game labels and folds.

direct_model         segment     n  season_date_clusters  delta_mae_mixture_minus_direct                                             ci95  bootstrap_reps
 direct_et12         overall 57682                   475                        -0.00247     [-0.013447891882411576, 0.00883953799349907]            3000
 direct_et12 actual_pdk_ge25 13104                   475                        -0.24762     [-0.28042083440125104, -0.21295573290203382]            3000
 direct_et12 actual_pdk_ge30  8794                   474                        -0.33231       [-0.3718696354160374, -0.2892246899695747]            3000
  direct_hgb         overall 57682                   475                        -0.00897 [-0.017608351685726123, -0.00021408333749637655]            3000
  direct_hgb actual_pdk_ge25 13104                   475                         0.01671     [-0.00812464218635997, 0.042526586209150105]            3000
  direct_hgb actual_pdk_ge30  8794                   474                         0.07000       [0.03711660005039429, 0.10236557589013823]            3000

## Interpretation

The mixture is only a candidate if overall MAE and high-score subgroup results improve without material degradation elsewhere. This bootstrap does not use 2025/26 or frozen prospective 2026/27 data and does not justify production promotion on its own.

No production code/config/weights changed; no commit or push.
