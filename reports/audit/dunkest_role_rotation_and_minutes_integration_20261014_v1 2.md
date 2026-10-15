# Role/rotation cohorts and minutes-model integration — 2026-10-14

## Decision

The predictive pipeline now has past-only team-transition/tenure and minute-volatility features, plus a separately trained HGB expected-minutes forecast exposed as `expected_min_model_shadow`. The minutes model is **not** used to replace `expected_min` or rescale `expected_pdk`: player-level temporal tests show a small minutes-MAE gain, but rescaling direct PDK forecasts worsens PDK MAE/RMSE. No fixed manual blend weight was added; the existing PDK ensemble weights continue to be learned from its own out-of-fold predictions.

## Role and history cohort audit

Source: `reports/audit/dunkest_role_rotation_cohort_audit_20261014_v3.md`, based on the outer walk-forward predictions for 2022/23–2024/25. Rookie status is an archive-derived debut-season proxy, low-history non-rookies are separately labeled, and team-change status is based on the previous observed team for the same NBA player. It is not an official transaction feed.

For the HGB ablation (MAE, lower is better):

| Cohort | N | Adapter features | Expanded lags | Rotation-aware features |
|---|---:|---:|---:|---:|
| All player-games | 57,682 | 7.5743 | 7.5615 | 7.5637 |
| Rookie/debut season proxy | 5,540 | 6.4827 | 6.3988 | 6.3916 |
| Low-history non-rookie | 338 | 5.0367 | 4.8764 | 4.8877 |
| Experienced team change | 555 | 6.9327 | 7.0260 | 6.8991 |
| Stable veteran | 43,545 | 7.9658 | 7.9843 | 7.9906 |

Expanded lags help the rookie/debut proxy and low-history non-rookies but slightly worsen the team-change cohort. Adding team-transition and volatility features recovers that team-change error (HGB MAE 7.0260 → 6.8991) while giving up about 0.0022 PDK in overall MAE versus expanded lags. That tradeoff is not enough to replace the overall PDK estimator on its own.

A nested team-change specialist experiment selected its weight using only the later-in-time 20% slice of the outer training block, separately in each fold. Selected rotation-model weights were 0.25, 1.00 and 0.00 for 2022/23, 2023/24 and 2024/25. The gated experiment reduced team-change MAE from 7.0393 to 6.9529 across 555 rows and pooled overall MAE from 7.5701 to 7.5693; RMSE moved from 9.8312 to 9.8308. The selected weight of zero in 2024/25 shows the specialist gain is not uniform enough to hard-code a separate production blend. Therefore the team-transition features are available to the production ensemble, but no separate fixed specialist weight was installed.

## Minutes model evidence

Source: `reports/audit/dunkest_minutes_hybrid_nested_20261014_v1.md`, with expanding-origin outer folds and train-only weight selection.

| Forecast | N | Minutes MAE | Minutes RMSE | Bias (predicted − actual) |
|---|---:|---:|---:|---:|
| Previous-5 minutes baseline | 57,500 | 5.1269 | 6.7808 | +0.0314 |
| HGB minutes model | 57,682 | 4.9839 | 6.4530 | +0.2943 |
| Nested cohort-gated hybrid | 57,682 | 4.9758 | 6.4619 | +0.2654 |
| Fixed 75% HGB / 25% baseline sensitivity | 57,682 | 4.9614 | 6.4551 | +0.2296 |

The HGB model improves minutes MAE over the previous-five baseline by about 0.143 minutes, but has a positive bias and is weaker on the low-history subgroup (5.6774 MAE vs 5.4906 for the baseline, on their available paired rows). The nested gate's total MAE gain over HGB is only about 0.008 minutes and its RMSE is worse. It does not justify hard-coding a minutes blend into the score calculation.

Downstream sensitivity is decisive: scaling the expanded-lag HGB PDK forecast toward the learned-minute ratio worsened PDK MAE from 7.5721 at zero scale weight to 7.5816 at only 10% scale weight, with RMSE also slightly worse. Full scaling raised MAE to 7.7646. Consequently, the minutes model is integrated as a shadow forecast only; the optimizer's score and roster objective are unchanged.

## Production implementation

- `src/dunkest/features/builder.py`: adds `team_changed_from_previous_game`, `team_history_known`, `team_games_since_change`, `min_std_5`, `min_zero_rate_5`, and `abs_min_last_vs_prev5`. All historical values are shifted/past-only; the inference team is overridden from the current market before transition features are finalized.
- `src/dunkest/models/multiseason_training.py`: joins verified historical NBA minutes by NBA game/player identity as a **label only** and computes the same past-only rotation features for the certified multi-season adapter.
- `src/dunkest/models/predictor.py`: trains an HGB minute model on `target_min` when sufficient matched labels exist and exports its forecast as `expected_min_model_shadow`. It is not included in `_weights`, is not used to compute `expected_pdk`, and does not alter the optimizer.
- `src/dunkest/report/terminal.py`: includes the shadow estimate in lineup-detail artifacts.
- Tests cover past-only minute volatility, team switches, current-team overrides, historical minute-label joins and the separation between shadow minutes and PDK ensemble weights.

## Production smoke test and automated checks

The exact multi-season trainer completed successfully after the changes: 93,766 certified PDK rows from 2020/21–2024/25, 56 active features, and 93,753 matched target-minute labels for the shadow model. The fitted PDK out-of-fold weights were Ridge 0.3343, Random Forest 0.3327 and Gradient Boosting 0.3330; the shadow model is not a member of those weights. These are the normal weights learned by the trainer, not hand-set coefficients. The 2025/26 holdout remained excluded.

A separate end-to-end prediction smoke test produced a non-null ML minutes estimate (17.98 minutes in the test fixture) while the roster's allocated-minutes estimate remained 23.95; `expected_pdk` was exactly identical with the shadow model enabled or disabled. This confirms the shadow output is surfaced without changing PDK scores.

Automated checks after the final changes: **398 tests passed** with deprecation warnings treated as errors; `py_compile` passed for the modified modules/experiments and `git diff --check` passed.

## Data and validation boundaries

- Outer folds: 2022/23, 2023/24 and 2024/25.
- The 2025/26 historical holdout and prospective 2026/27 GW1 bundle were excluded from all tuning.
- Target-game NBA minutes are used only as supervised labels/evaluation targets, never as features.
- No realized-lineup validation was used as an objective.
- No commit or push performed.
