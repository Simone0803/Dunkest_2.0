# Predictive model enrichment — player lags, minutes and high-score cohorts

Generated: 2026-10-14

## Objective and constraints

This pass prioritizes individual-player forecasts and model features, not realized lineup validation. All comparisons use expanding-origin folds for 2022/23, 2023/24 and 2024/25, based on verified Dunkest player-game labels and past-only features. The 2025/26 holdout and frozen 2026/27 GW1 prediction bundle were not loaded. No tuning uses realized lineup scores.

## 1. Promoted feature enrichment

The production feature schema and feature builder now include explicit lagged signals that the historical training archive already contains and that the live feature builder can calculate without looking at the target game:

- Dunkest PDK lags 1–5 and short-vs-long PDK trend (previous 3 vs previous 10).
- NBA minutes lags 1–3, recent-three minutes mean, recent-three-vs-five minutes trend and last-game-vs-five-game minutes delta.
- NBA points, rebounds and assists lags 1–3 and previous-three means.
- Separate Dunkest-history and NBA-history game counts to help the model distinguish limited Dunkest history from general NBA experience.

The historical adapter maps these columns from the certified training archive. The live builder derives them using shifts and rolling windows, with current-game statistics never included. The model trainer's all-data fit succeeded on 93,766 certified rows; **50 finite features** were selected after all-missing columns were dropped. Current-season official labels appended: 0, as expected before the 2026/27 regular season begins. Learned weights on this final fit were Ridge 0.3335, Random Forest 0.3329 and Gradient Boosting 0.3337. These are training/OOF ensemble weights, not an independent estimate of next-season performance.

### Walk-forward ablation results

The numeric-only ablation compared the production-adapter feature set (24 observed features) against the expanded lag feature set (50 features) using the same estimator families and the same 57,682 player-game rows. It did not add categorical team/opponent features. A 50/50 blend of ExtraTrees and HistGradientBoosting is shown to test whether the enriched signals help both overall prediction and high-score tails.

| Candidate | MAE | RMSE | Bias (pred − actual) | MAE actual PDK ≥25 | MAE actual PDK ≥30 | MAE history <5 games |
|---|---:|---:|---:|---:|---:|---:|
| Adapter features, ET/HGB 50/50 | 7.5796 | 9.8783 | −0.4033 | 12.4927 | 14.4992 | 5.2133 |
| Expanded lags, ET/HGB 50/50 | **7.5570** | **9.8192** | −0.0502 | **12.1285** | **14.0882** | **5.1447** |

The expanded blend reduced MAE by **0.0226 PDK** and RMSE by **0.0591** on the same rows. A paired bootstrap resampling 475 target-date clusters gave a MAE delta (expanded minus adapter blend) of **−0.02258**, 95% CI **[−0.03270, −0.01239]**. All three held-out seasons improved in the feature ablation:

| Season | Adapter blend MAE | Expanded blend MAE | Adapter blend RMSE | Expanded blend RMSE |
|---|---:|---:|---:|---:|
| 2022/23 | 7.5790 | 7.5568 | 9.8887 | 9.8149 |
| 2023/24 | 7.5642 | 7.5547 | 9.8444 | 9.7905 |
| 2024/25 | 7.5951 | 7.5595 | 9.9007 | 9.8510 |

This is evidence that the feature enrichment is useful, not a guarantee that the exact production ensemble will improve by the same amount. The production model now trains with the expanded schema and retains its own temporal out-of-fold weighting/calibration. No fixed 50/50 ET/HGB blend was installed as the production estimator.

### Exact production trainer, held-out seasons

I then ran the exact production `train_multiseason_models` / `train_models` pipeline separately before each held-out season, with its own inner OOF ensemble-weight fitting. On the same 57,682 outer-fold rows, it achieved MAE **7.5573** and RMSE **9.8230**, versus the previous-10 PDK mean baseline at MAE **7.7756** and RMSE **10.1316**. Its pooled low-history MAE (<5 Dunkest games) was **5.2229**, versus **6.3477** for that baseline. However, the high-score cohorts remain a weakness: actual PDK ≥25 MAE was **12.1888** versus **12.0176** for the baseline, and actual PDK ≥30 MAE was **14.1802** versus **13.7098**. This is why the next step is a nested, train-only test of a conditional high-score component rather than immediately increasing rookie weights or changing the optimizer objective.

Exact trainer report: `reports/audit/dunkest_production_trainer_walk_forward_20261014_v1.md`, with metrics, predictions and fold-specific weights.

A subsequent nested temporal test of a conditional high-score component selected tail weights 0.25, 0.25 and 0.50 in the three training-only validation folds. On the external folds, the blend lowered MAE from 7.5573 to **7.5477** and RMSE from 9.8230 to **9.8119**. Paired date-cluster bootstrap (10,000 resamples, 475 clusters) estimated ΔMAE = −0.00958 PDK, 95% CI [−0.01243, −0.00667]. The tail component alone improved errors among realized ≥25 and ≥30 PDK players more than the blend, but its overall MAE was marginally worse than production. The blend is therefore **not promoted**: the gain is small, and the ≥30 cohort is not uniformly improved fold-by-fold. The no-prior-Dunkest-history subset contains only 249 player-games and is not a substitute for a verified rookie cohort. Details: `reports/audit/dunkest_production_tail_blend_nested_20261014_v1.md`.

The follow-up role/rotation investigation is complete. Past-only team-change/tenure and minute-volatility features are now included in the production feature builder and the certified multi-season adapter. The minute model is trained separately from matched NBA minutes labels and surfaced as `expected_min_model_shadow`; it is explicitly excluded from the PDK ensemble and optimizer because downstream PDK rescaling worsened out-of-sample error. Full decision and verification details: `reports/audit/dunkest_role_rotation_and_minutes_integration_20261014_v1.md`.

Artifacts: `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2.md`, `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2_metrics.csv`, `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2_predictions.csv` and `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2.json`.

## 2. Expected-minutes experiment — not promoted as a standalone production forecast

A separate minute-regression walk-forward experiment compared recent-minute baselines with ExtraTrees, Random Forest and HistGradientBoosting. On 57,500 paired rows, HistGradientBoosting reached MAE **4.9749 minutes** and RMSE **6.4423**, versus previous-five mean MAE **5.1269** and RMSE **6.7808**. However, it introduced positive bias (+0.285 minutes vs +0.031), lowered the share of predictions within five minutes (59.48% vs 60.31%) and worsened error on observed zero-minute games (10.65 vs 9.44 minutes).

Therefore, the standalone minute model was not inserted into the score calculation or the minutes allocator. It lacks current CR/Lineups role context and can overestimate non-playing outcomes. Production keeps the existing role/CR/availability-aware minutes logic. The minute model remains an auditable research candidate; a future integration must first combine its forecast with live role and play-probability evidence and show better downstream PDK forecasts, not just lower minutes MAE.

Artifact: `reports/audit/dunkest_minutes_forecast_walk_forward_20261014_v1.md` and accompanying CSV/JSON.

## 3. High-score forecasts

The enriched lags improve both PDK ≥25 and PDK ≥30 segments in the direct-regression ablation. The separate conditional-tail V2 remains research-only: its pooled overall MAE gain over direct models is small and it does not dominate the strongest direct model in every tail metric. No tail-specific estimator was promoted in this pass.

## 4. Tests and safeguards

- Full suite: **396 passed** with `-W error::DeprecationWarning`.
- `py_compile` and `git diff --check` passed.
- New tests assert that recent PDK/minutes/stat lags and history counts use only past rows and that the certified historical adapter maps the same feature schema.
- No realized-lineup metrics were used to select features.
- The 2026/27 GW1 holdout remains frozen until 2026-10-23 12:00 UTC.
- No commit or push performed.

## Next steps

1. Run the same expanding-origin evaluation through the exact production trainer with the enriched schema, comparing MAE/RMSE/bias and the PDK ≥25, PDK ≥30 and low-history cohorts by season.
2. Review feature importance/stability by fold to ensure the new gains are not concentrated in one season or one player subgroup.
3. Investigate minutes residuals specifically for likely DNP/rotation-change cases, while keeping Lineups status, current CR and `p_play` as distinct evidence rather than letting historical minutes override them.
4. Do not alter rookie weights or production risk settings without a separate past-only cohort comparison.
