# Proxy-target vs official-target training — 2025/26 (v2, common-row comparison)

- Common OOF rows from both target modes: **7,407**
- Rows used for every model and baseline metric: **7,384** (all rows have both model predictions and both baselines)
- Rows omitted only because a baseline feature was unavailable: **23**
- Dates: **2026-01-30 – 2026-04-10** across 64 dates
- Evaluation target: official PDK, restricted to rows with verified official labels and `gameValidForDunkest=True`.

## Main comparison (identical rows)

| Model/predictor | N | MAE vs official | RMSE vs official | Bias | R² | P90 absolute error |
|---|---:|---:|---:|---:|---:|---:|
| trained_on_proxy__evaluated_vs_official | 7384 | 7.5510 | 9.8782 | -0.6783 | 0.4049 | 15.9189 |
| trained_on_official__evaluated_vs_official | 7384 | 7.5651 | 9.8461 | -0.1679 | 0.4088 | 15.9473 |
| proxy_previous_10_mean__evaluated_vs_official | 7384 | 7.7223 | 10.1718 | -0.7173 | 0.3690 | 16.3839 |
| minutes_projection__evaluated_vs_official | 7384 | 7.5743 | 9.9598 | -0.9108 | 0.3951 | 16.1026 |

## Error by official target band

| Official PDK band | Model | N | MAE | RMSE | Bias |
|---|---|---:|---:|---:|---:|
| <5 | trained_on_proxy | 1527 | 7.9238 | 9.5300 | 7.8677 |
| <5 | trained_on_official | 1527 | 8.1687 | 9.8455 | 8.1107 |
| 5-10 | trained_on_proxy | 1251 | 5.6876 | 7.2430 | 4.7978 |
| 5-10 | trained_on_official | 1251 | 6.0411 | 7.6662 | 5.1810 |
| 10-20 | trained_on_proxy | 2146 | 4.6627 | 5.9363 | 0.5378 |
| 10-20 | trained_on_official | 2146 | 4.8795 | 6.2182 | 1.0619 |
| 20-30 | trained_on_proxy | 1425 | 7.2276 | 8.6692 | -5.7301 |
| 20-30 | trained_on_official | 1425 | 6.9368 | 8.4194 | -5.0637 |
| 30+ | trained_on_proxy | 1035 | 15.6872 | 17.9502 | -15.4715 |
| 30+ | trained_on_official | 1035 | 14.9502 | 17.3155 | -14.6562 |

## Proxy-versus-official label difference

- Mean proxy-minus-official: **-0.5040 PDK**
- MAE between proxy and official labels: **0.5099 PDK**
- RMSE between proxy and official labels: **0.7289 PDK**
- P90 absolute difference: **1.0525 PDK**

## Conclusion

The result is mixed: the proxy-trained model has slightly lower MAE against official PDK, while the official-trained model has slightly lower RMSE and substantially less negative bias. This does not justify changing the production target mode by itself. The comparison uses identical rows/cutoffs and proxy-derived lag features in both arms; no production behavior or existing data/model artifacts were changed.
