# Dunkest end-to-end model audit — 2026-10-14

## Scope

Reviewed the production prediction path and linked research artifacts: data access and label joins; rolling player/team features; temporal validation; primary and historical PDK models; rookie priors; availability and minutes; score uncertainty; plusvalenza; coach scoring; lineup optimization; run manifests and backtest readiness. Existing walk-forward and data-provenance audits were used to avoid treating the already-examined 2025/26 season as a pristine holdout.

## Changes applied

1. **Official PDK now feeds lagged PDK features when verified.** PDK_OFFICIAL_VALID is preferred over the NBA-boxscore proxy for rolling means, medians, standard deviations, season PDK/minute rates and opponent history; the proxy is retained only where an official score is unavailable. Current-game target columns remain separate and rolling features shift before aggregation.
2. **Ambiguous player/date rows fail closed.** The feature builder rejects duplicate player/date records instead of letting shift(1) depend on arbitrary row order. Game ID is used as a stable sort key after the uniqueness check.
3. **Nullable identity/status handling is robust.** player_key, injury status parsing, injury matching and coach matchup-date fallback no longer evaluate pandas.NA as a boolean.
4. **Coach simulation no longer produces tied final scores.** Rounded score ties are resolved as overtime outcomes, and the score distribution and win-probability diagnostics now share the same seeded score generator.
5. **Neutral coach estimates are labelled honestly.** A verified fixture with no team-history model is tagged verified_matchup_neutral_baseline, not as a fully modelled matchup. The optimizer does not treat this source as a verified strength projection.
6. **Training-label provenance is saved in each run manifest.** The manifest records target name/source, number of training rows, number of available official labels and the training date range.
7. Added regression tests for the above behaviours.

## Measured ablation: official vs proxy PDK history

The paired diagnostic used the same 2025/26 rows and official PDK targets, changing only whether lagged PDK history used verified official scores or proxy scores. It disabled schedule, matchup and injury features to isolate this change.

| Metric | Official PDK history | Proxy-only history |
|---|---:|---:|
| OOF rows scored | 7,295 | 7,295 |
| MAE | 7.6495 | 7.6571 |
| RMSE | 9.9235 | 9.9320 |
| MAE when actual PDK ≥25 | 12.2812 | 12.3159 |
| MAE when actual PDK ≥30 | 14.9159 | 14.9424 |

This is a **small but consistent improvement** (overall MAE improves by about 0.10%; tail MAE by about 0.28% for PDK≥25). The 2025/26 season has already been examined elsewhere in the project, so this is an exploratory ablation, not an untouched final holdout. The result supports retaining official-score history, but it does not justify changing model weights by itself.

Reproducible artifacts:
- scripts/audit_dunkest_official_vs_proxy_history_features_v1.py
- reports/audit/dunkest_official_vs_proxy_pdk_history_features_20261014_v1.json

## High-priority issues still open

### 1. The primary GW1 trainer is not yet multi-season

src/dunkest/pipeline/train.py trains the main model on player_game_logs_<feature_season>.parquet for GW1. The multi-season certified PDK dataset is used by a separate historical-model path, blended into the prediction, rather than as the primary trainer. This does not yet implement the intended full policy of supervised training on certified 2020/21–2024/25 data.

The historical schema and the production feature schema are not interchangeable. Replacing the trainer without a careful adapter could introduce distribution shifts or target leakage. Next step: construct a common, strictly as-of feature matrix and compare single-season vs multi-season training on expanding-origin season folds before promoting it.

### 2. Official-target fallback remains a policy decision

training_target=auto still falls back to proxy PDK when fewer than 1,000 official labels are available. The new manifest provenance makes this visible, but experiments that claim official-target training must explicitly select target_pdk_official and fail if certified labels are insufficient. Do not compare metrics across different target sources as if they were the same task.

### 3. The 2018/19 and 2019/20 archive rows are not certified Dunkest targets

The existing archive marks all rows in those two seasons as invalid for Dunkest scoring. They can provide NBA history/features, but should not be used as supervised Dunkest PDK targets without a separate authoritative verification. Certified supervised PDK training currently begins in 2020/21.

### 4. A new model must be validated without reusing the examined holdout

2025/26 has already been used in multiple comparison, calibration and error-slice experiments. Keep it as a historical fold with this caveat; do not call it a project-wide untouched holdout. Select features, ensemble weights and calibration on earlier expanding-origin folds, then evaluate once on a genuinely new future period.

### 5. Risk-adjusted optimization is not yet proven superior on realized lineups

The current risk_lambda=0.10 reduces forecast spread, but that is not proof it increases realized Dunkest score. The October 13 frozen GW1 forecast and required snapshots are about 149–151 hours old at the earliest mapped tip-off, so they are exploratory only. The strict V3 strategy builder correctly rejects them as stale. A decisive comparison requires a new pre-lock run with fresh timestamped snapshots, then official fixture-linked player and coach results.

### 6. Questionable-player policy is conservative and needs a measured ablation

The optimizer currently excludes players with p_play < 1.0. This avoids selecting doubtful players, but can reject valuable players with non-zero availability. Compare this hard exclusion against availability-adjusted expected value and risk-adjusted value in historical pregame snapshots; do not change the policy based only on intuition.

## Further precision work, in priority order

1. Expand official-label coverage and audit every unmatched player/game join. The current 2025/26 official overlay matched 24,098 of 24,146 rows; 48 remain unmatched. Preserve unmatched rows as missing, never as zero.
2. Build a multi-season primary-model challenger using certified 2020/21–2024/25 PDK labels and strictly past-only features. Use 2018/19–2019/20 only as NBA feature history unless labels are certified.
3. Report MAE, RMSE, bias and interval coverage by season, history length, minutes, role, rookie status and high-score cohort. Keep model selection/calibration fold-local.
4. Validate the full score chain separately: player score, availability/minutes, coach score, captain multiplier, transfer malus and plusvalenza. Use verified official realized scores and fixture links.
5. Tune risk penalty, plusvalenza weight and questionable-player policy only on out-of-sample lineup outcomes; retain a future holdout.
6. Reduce PuLP deprecation warnings before the PuLP 4.0 transition; these warnings do not currently cause test failures but make test output noisy.

## Verification

- Targeted tests passed after the nullable-value, official-history and coach-simulation fixes.
- Final full suite: **289 passed** in 16.26 seconds.
- The suite emits about 6,800 PuLP deprecation warnings and one expected warning for a test market file without freshness metadata.
- No model weights were changed based on the exploratory ablation. No commit or push was performed.
