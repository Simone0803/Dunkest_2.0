# Dunkest — Phase B model and strategy comparison
Generated: 2026-10-13

## Executive decision

**Keep production model weights and target mode unchanged.** The chronological feature-family comparison supports combining prior official PDK history with prior NBA boxscore history. However, the marginal benefit of the current categorical opponent features is effectively zero, the official-versus-proxy target comparison is mixed, and no authentic historical complete-lineup backtest can yet score lineup/coach/transfer strategy.

## 1. Player PDK feature families

Expanding-origin training, one season held out at a time. Selection uses only 2022/23, 2023/24 and 2024/25 (57,682 player-game observations pooled). Each model uses the same Extra Trees settings; only the feature family changes.

| Feature family | Features | Weighted MAE | Weighted RMSE | Weighted bias |
|---|---:|---:|---:|---:|
| Combined: PDK + NBA + opponent | 79 | 7.5670 | 9.8382 | -0.1702 |
| Combined without opponent categories | 77 | 7.5672 | 9.8397 | -0.1595 |
| NBA history + opponent | 69 | 7.6238 | 9.9606 | -0.5783 |
| Previous-10 PDK mean baseline | 1 | 7.7756 | 10.1316 | -0.0307 |
| PDK history + opponent only | 12 | 7.8326 | 10.0761 | +0.2679 |

The combined family improves MAE by 0.2085 PDK (2.68%) over the previous-10 baseline and by 0.0567 (0.74%) over NBA history plus opponent categories. PDK history alone does not perform well as a stand-alone model; its useful signal appears when combined with NBA history.

The opponent categorical variables reduce pooled validation MAE by only 0.00019 versus the same model without them. This is negligible and does **not** demonstrate that detailed matchup logic is unnecessary; the tested features are only opponent team code and opponent position, not a rich defensive matchup model.

### Secondary historical 2025/26 fold

| Feature family | MAE | RMSE | Bias |
|---|---:|---:|---:|
| Combined: PDK + NBA + opponent | 7.5639 | 9.8383 | -0.1682 |
| Combined without opponent categories | 7.5677 | 9.8420 | -0.1472 |
| NBA history + opponent | 7.6290 | 9.9472 | -0.4276 |
| PDK history + opponent only | 7.7676 | 10.0344 | +0.1144 |
| Previous-10 PDK mean baseline | 7.7886 | 10.1539 | -0.0479 |

2025/26 is included only as a secondary historical comparison. It was already examined by earlier project experiments, so it is not a globally untouched holdout and must not be used to claim a clean final generalization estimate.

## 2. Cold-start / low-history behavior

The feature-family experiment defines cohorts by the number of previous valid Dunkest PDK games, not by NBA draft class. On validation seasons pooled:

| Prior PDK history cohort | N | Combined MAE | Baseline MAE |
|---|---:|---:|---:|
| No prior valid PDK game | 249 | 5.1360 | 9.6840 |
| 1–3 prior games | 736 | 5.0181 | 5.3502 |
| 4–10 prior games | 1,588 | 5.4456 | 5.5499 |
| More than 10 prior games | 55,109 | 7.6732 | 7.8635 |

The combined feature family materially reduces cold-start error relative to a previous-10 PDK baseline, because the baseline has no usable player history and falls back to the training median. These are low-history cohorts, **not** proof of performance on verified NBA rookies.

The separate rookie-prior audit remains the more relevant evidence: college-to-NBA PDK/minute rate MAE was 0.1100 versus 0.1240 for the historical rookie-rate baseline; conditional rookie minutes MAE was 5.84 versus 7.35 for a historical position/overall median baseline. Because the minute estimate is conditional on observed NBA rookie minutes, its blend cap was reduced from 35% to 15%. This is a conservative integration safeguard, not evidence of an out-of-sample improvement to complete Dunkest lineups.

## 3. Official target versus proxy target

Existing common-row 2025/26 comparison (7,384 rows, identical rows and evaluation against official PDK):

| Model training target | MAE | RMSE | Bias |
|---|---:|---:|---:|
| Proxy-trained, evaluated against official PDK | 7.5510 | 9.8782 | -0.6783 |
| Official-target-trained, evaluated against official PDK | 7.5651 | 9.8461 | -0.1679 |
| Previous-10 PDK mean | 7.7223 | 10.1718 | -0.7173 |

The result is mixed: proxy training has slightly lower MAE; official-target training has lower RMSE and much less negative bias. The two arms used proxy-derived lag features, and the comparison covers a subset of the season. **No production target-mode switch is justified by these metrics alone.**

## 4. Team and coach strategy evidence

Existing team-score/win-probability audits support keeping the points-only team-score baseline:
- 2025/26 team margin MAE: 11.446 points; home/away team-points MAE: 10.009 / 9.443.
- Raw win-probability Brier score / log loss: 0.2066 / 0.6014; accuracy 68.7%.
- The efficiency blend did not improve both validation Brier and log loss.
- The PDK-derived roster-strength proxy worsened validation Brier from 0.2098 to 0.2102 and log loss from 0.6066 to 0.6076.
- Platt calibration slightly worsened 2025/26 Brier/log loss (0.2066 / 0.6014 to 0.2067 / 0.6015).

These are NBA team outcome metrics, not realized Dunkest coach fantasy-score metrics. They do not justify changing coach fantasy scoring, matchup weights, or transfer strategy.

## 5. Complete-lineup backtest status

**Not ready — no complete-lineup strategy winner can be declared.**

The readiness audit found one round checked and zero rounds passing all requirements. Fixture mapping, roster/credits, timestamped injuries and fixture-linked coaches passed; fixture-linked realized player results and coach results did not. Historical weekly outcome tables cannot establish the exact pre-match CR, injuries, availability and coach market. Using them as if they were known before tip-off would create look-ahead bias.

Therefore this phase does not claim any validated advantage for expected-value versus risk-adjusted lineup selection, alternative risk penalties, transfer/malus policies, complete team score combining players/coach/transfers, or coach selection at Dunkest fantasy-score level.

Those comparisons require authentic frozen pre-match snapshots and official player/coach outcomes linked to the same fixture IDs. The frozen 2026/27 GW1 prospective run is preserved for later post-match evaluation.

## 6. Phase B decisions

1. Keep the combined PDK + NBA feature family as the leading research candidate, not yet as a production replacement.
2. Do not prioritize opponent team code/position features; their measured marginal contribution is negligible. A richer matchup feature should be proposed and tested as a separate walk-forward ablation before any change.
3. Do not switch official/proxy target mode yet; the existing comparison is mixed and uses a partial common-row sample.
4. Preserve the reduced 15% cap on the college-derived rookie-minute prior; do not increase it without a participation-aware, chronological validation.
5. Keep points-only raw team win probabilities; do not deploy the tested efficiency blend, roster-strength proxy or Platt calibration.
6. Do not report complete-lineup strategy metrics until fixture-linked realized player and coach outcomes and authenticated pre-match state are available.
7. Keep production configuration and weights unchanged pending paired end-to-end lineup validation.

## Reproducible artifacts

- Feature-family experiment: scripts/compare_dunkest_pdk_feature_families_walk_forward_v1.py
- Feature-family report: reports/audit/dunkest_pdk_feature_families_20261013_v1.md
- Fold metrics: reports/audit/dunkest_pdk_feature_families_metrics_20261013_v1.csv
- Cohort metrics: reports/audit/dunkest_pdk_feature_families_cohorts_20261013_v1.csv
- Per-row predictions: reports/audit/dunkest_pdk_feature_families_predictions_20261013_v1.csv
- Structured audit: reports/audit/dunkest_pdk_feature_families_audit_20261013_v1.json
- Official versus proxy target report: reports/audit/proxy_vs_official_target_comparison_2025-26_v2.md
- Rookie-prior audit: reports/audit/dunkest_rookie_balance_20261012T171217Z_2f98f42b_v1.md
- Consolidated backtest status: reports/audit/dunkest_pdk_backtest_summary_20261013_v1.md
- Complete-lineup readiness: reports/audit/dunkest_lineup_backtest_readiness_v2.md

## Integrity notes

All experiment artifacts are separately versioned. No production weights, configurations, historical source datasets, or frozen prospective run artifacts were modified. Model feature-family predictions are player-game forecasts only; they are not lineup-score backtest results.
