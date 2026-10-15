# Proxy-target vs official-target training — 2025/26 (v1)

- Common labelled rows before OOF: **18,412**
- Identical OOF evaluation rows: **7,407** across 64 dates (2026-01-30 to 2026-04-10)
- Evaluation target: official PDK, restricted to rows with a verified official label and `gameValidForDunkest=True`.

## Main comparison

| Model/predictor | N | MAE vs official | RMSE vs official | Bias | R² | P90 absolute error |
|---|---:|---:|---:|---:|---:|---:|
| model_trained_on_proxy_target__evaluated_vs_official | 7407 | 7.5480 | 9.8786 | -0.6759 | 0.4051 | 15.9153 |
| model_trained_on_official_target__evaluated_vs_official | 7407 | 7.5627 | 9.8465 | -0.1658 | 0.4089 | 15.9449 |
| baseline_proxy_previous_10_mean__evaluated_vs_official | 7384 | 7.7223 | 10.1718 | -0.7173 | 0.3690 | 16.3839 |
| baseline_minutes_projection__evaluated_vs_official | 7384 | 7.5743 | 9.9598 | -0.9108 | 0.3951 | 16.1026 |

## Error by official target band

| Official PDK band | Model | N | MAE | RMSE | Bias |
|---|---|---:|---:|---:|---:|
| <5 | trained_on_proxy | 1540 | 7.9045 | 9.5057 | 7.8488 |
| <5 | trained_on_official | 1540 | 8.1509 | 9.8213 | 8.0934 |
| 5-10 | trained_on_proxy | 1258 | 5.6632 | 7.2238 | 4.7695 |
| 5-10 | trained_on_official | 1258 | 6.0148 | 7.6458 | 5.1525 |
| 10-20 | trained_on_proxy | 2147 | 4.6657 | 5.9399 | 0.5323 |
| 10-20 | trained_on_official | 2147 | 4.8823 | 6.2211 | 1.0564 |
| 20-30 | trained_on_proxy | 1425 | 7.2276 | 8.6692 | -5.7301 |
| 20-30 | trained_on_official | 1425 | 6.9368 | 8.4194 | -5.0637 |
| 30+ | trained_on_proxy | 1037 | 15.7131 | 17.9785 | -15.4978 |
| 30+ | trained_on_official | 1037 | 14.9763 | 17.3441 | -14.6829 |

## Label difference

- Mean proxy-minus-official difference: **-0.5031 PDK**
- MAE between proxy and official labels: **0.5090 PDK**
- RMSE between proxy and official labels: **0.7283 PDK**
- P90 absolute label difference: **1.0525 PDK**

## Limits and safety

This experiment uses identical chronological OOF cutoffs and the same official-valid rows for both target modes. It isolates target choice under the production feature builder, so both arms use proxy-derived lag features. It is not a full multi-season validation and does not alter production configuration, model artefacts, source data, or existing backtests.
