# Multi-season player PDK: temporal baselines — 2026-10-18 V1

Generated UTC: 2026-10-18T09:34:14.567115+00:00

## Method

- Reused 57,682 saved OOS player-game predictions from the current production multi-season adapter.
- Test seasons: 2022/23, 2023/24 and 2024/25. No refit, 2025/26 holdout, or prospective GW1 results were used.
- Baselines use only prior official PDK and strictly prior NBA minutes. For each baseline, model metrics use the identical rows with a finite baseline.
- Paired uncertainty resamples game dates within each season, then averages seasons equally.

## Pooled paired results

| Baseline | Rows | Coverage | Baseline MAE | Model MAE on same rows | Δ MAE (model − baseline) | 95% date-cluster interval |
|---|---:|---:|---:|---:|---:|---:|
| previous_3_official_pdk_mean | 57,433 | 99.6% | 8.3193 | 7.5209 | -0.7983 | [-0.8347, -0.7293] |
| previous_5_official_pdk_mean | 57,433 | 99.6% | 7.9749 | 7.5209 | -0.4540 | [-0.4990, -0.4146] |
| previous_10_official_pdk_mean | 57,433 | 99.6% | 7.7673 | 7.5209 | -0.2463 | [-0.2785, -0.2193] |
| past_season_official_pdk_mean | 57,433 | 99.6% | 7.7151 | 7.5209 | -0.1941 | [-0.2199, -0.1558] |
| past_official_pdk_per_min_x_previous_5_nba_minutes | 57,425 | 99.6% | 7.6855 | 7.5215 | -0.1640 | [-0.1921, -0.1197] |

## Per-season metrics

| Baseline | Season | N | Coverage | Baseline MAE | Model MAE on same rows | Δ MAE |
|---|---|---:|---:|---:|---:|---:|
| previous_3_official_pdk_mean | 2022-23 | 19,086 | 99.6% | 8.2941 | 7.5258 | -0.7683 |
| previous_3_official_pdk_mean | 2023-24 | 18,839 | 99.5% | 8.3107 | 7.5055 | -0.8052 |
| previous_3_official_pdk_mean | 2024-25 | 19,508 | 99.6% | 8.3522 | 7.5311 | -0.8211 |
| previous_5_official_pdk_mean | 2022-23 | 19,086 | 99.6% | 7.9702 | 7.5258 | -0.4444 |
| previous_5_official_pdk_mean | 2023-24 | 18,839 | 99.5% | 7.9591 | 7.5055 | -0.4535 |
| previous_5_official_pdk_mean | 2024-25 | 19,508 | 99.6% | 7.9949 | 7.5311 | -0.4638 |
| previous_10_official_pdk_mean | 2022-23 | 19,086 | 99.6% | 7.7635 | 7.5258 | -0.2377 |
| previous_10_official_pdk_mean | 2023-24 | 18,839 | 99.5% | 7.7546 | 7.5055 | -0.2491 |
| previous_10_official_pdk_mean | 2024-25 | 19,508 | 99.6% | 7.7832 | 7.5311 | -0.2521 |
| past_season_official_pdk_mean | 2022-23 | 19,086 | 99.6% | 7.6951 | 7.5258 | -0.1693 |
| past_season_official_pdk_mean | 2023-24 | 18,839 | 99.5% | 7.7136 | 7.5055 | -0.2080 |
| past_season_official_pdk_mean | 2024-25 | 19,508 | 99.6% | 7.7361 | 7.5311 | -0.2050 |
| past_official_pdk_per_min_x_previous_5_nba_minutes | 2022-23 | 19,081 | 99.6% | 7.6809 | 7.5269 | -0.1540 |
| past_official_pdk_per_min_x_previous_5_nba_minutes | 2023-24 | 18,837 | 99.5% | 7.6411 | 7.5061 | -0.1350 |
| past_official_pdk_per_min_x_previous_5_nba_minutes | 2024-25 | 19,507 | 99.6% | 7.7329 | 7.5309 | -0.2020 |

## Interpretation and limits

- Historical validation folds are not a pristine project-wide holdout.
- Coverage differs across simple baselines because players without enough prior official history have no direct seasonal/rate estimate; model metrics are reported on each baseline's same rows.
- Player-score comparisons do not validate coach scores, lineup policy, credits, injuries or transfer strategy.
- 2025/26 and 2026/27 prospective outcomes were not loaded or used.

## Reproduction

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_multiseason_temporal_baselines_20261018_v1.py
```

## Artifacts

- `reports/audit/dunkest_multiseason_temporal_baselines_20261018_v1.json`
- `reports/audit/dunkest_multiseason_temporal_baselines_20261018_v1.md`
- `reports/audit/dunkest_multiseason_temporal_baselines_20261018_v1_metrics.csv`
