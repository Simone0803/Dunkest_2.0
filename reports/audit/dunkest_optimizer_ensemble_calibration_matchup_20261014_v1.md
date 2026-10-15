# Dunkest optimizer, ensemble, calibration and matchup audit — 2026-10-14

## Decision summary

**No production weight, risk coefficient, calibration, matchup feature, or lineup objective is changed in this task.** Existing out-of-sample experiments support keeping the current production path while retaining several challengers for further validation. The main blocker for optimizer-level promotion is the lack of authentic historical pre-lock market/roster snapshots and fully fixture-linked realized team scores.

## 1. Ensemble weights and predictor hyperparameters

### Ensemble weights

The existing expanding-window search in `scripts/tune_dunkest_ensemble_weights_walk_forward_v1.py` selected weights on 2022/23–2024/25 only, minimizing pooled player-game MAE over 231 convex combinations on a 0.05 grid:

| Component | Weight |
|---|---:|
| Random Forest | 0.60 |
| Ridge | 0.35 |
| Previous-10 PDK mean | 0.05 |

Validation MAE was 7.5658 PDK (57,682 rows). The archived 2025/26 comparison was MAE 7.5568, RMSE 9.8306, bias −0.0885. This historical test was not used for that search, but the season has since been inspected by other project experiments and is not a globally untouched holdout. The weights are therefore evidence for a challenger, not a mandate to overwrite current production weights.

### Hyperparameter/model search

The existing train-only expanding-origin search selected `extra_trees_deep` at weighted validation MAE 7.56350 and RMSE 9.83284 over 2022/23–2024/25. RF baseline MAE was 7.58796. The 2025/26 historical comparison was MAE 7.56126 and RMSE 9.83753 versus RF MAE 7.57748 and RMSE 9.85634. The improvement is small. The saved candidate still uses a feature schema not wired to the production inference path, so it is not promoted.

Source report: `reports/audit/dunkest_pdk_model_tuning_20261012_v1.md`.

## 2. Probability and uncertainty calibration

### Player/coach availability probabilities

The historical NBA appearance-continuity proxy has a positive target rate of 99.64%–99.79% among observed target rows, and 52,171 candidate-game rows were unlabeled. It cannot validate production Dunkest `p_play`; a low Brier score here is mostly a consequence of the near-constant positive class. Do not train or promote an availability probability from this proxy as if missing rows were verified OUT/DNP.

### Coach win probabilities

The Platt-calibration candidate was evaluated with 2024/25 validation after fitting on earlier seasons. Brier worsened from 0.209783 to 0.209846 and log loss from 0.606641 to 0.606830; it was correctly rejected. On the 2025/26 historical holdout, raw Brier/log loss were 0.206582/0.601394 versus calibrated 0.206678/0.601503. Keep raw probabilities until a different calibrator shows consistent gains on genuinely future validation.

### Expanding-origin residual interval audit

New report: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2.md`.

This audit uses saved walk-forward Random Forest predictions and certified targets; for each test season, residual quantiles are fitted only on earlier OOF seasons. Across 2023/24–2025/26, pooled residual intervals achieved:

| Test season | Lower-tail coverage | Upper-tail coverage | Central 80% coverage | Mean width (PDK) |
|---|---:|---:|---:|---:|
| 2023/24 | 89.53% | 90.27% | 79.80% | 24.32 |
| 2024/25 | 89.90% | 90.52% | 80.42% | 24.32 |
| 2025/26 | 89.95% | 90.27% | 80.22% | 24.20 |

Coverage is close to nominal in these rolling folds. Cohort-specific residual quantiles substantially narrow intervals for players with 0–5 prior Dunkest rows: on 2025/26, width 15.62 PDK versus 24.20 pooled, with lower/upper coverage 89.89%/89.89% and central coverage 79.77%. The 6–10 history cohort has only 387 test rows in 2025/26 and central coverage 76.49%; this is too weak to promote unconditionally. The high-history cohort changes little.

**Decision:** retain pooled calibration in production for now. The cohort-specific approach is a promising challenger, especially for low-history players, but the audit uses an RF proxy rather than the current multi-model production ensemble. Refit and validate the calibration on the actual production ensemble's cross-fitted residuals before deployment. A separate first-version audit file had the sign of the residual-to-score interval inversion wrong; the corrected and authoritative results are in the `_v2` report.

## 3. Player and coach matchup logic

### Player matchup features

- The expanded lagged matchup model improved game-level MAE from 7.52094 (lagged credit + historical form) to 7.50275, but the role-interaction challenger did not add meaningful value: pooled MAE 7.502699 versus 7.502754, paired delta −0.000055 PDK, 95% cluster-bootstrap interval [−0.004265, +0.004187].
- H2H features modestly improved player-game prediction in one experiment but failed to transfer to lineup selection. The paired lineup audit found H2H lineups scored 5.66 fewer realized proxy points per round than the otherwise comparable model without H2H; 95% paired interval [−9.49, −1.77] over 409 rounds.

**Decision:** keep the validated base matchup terms available for continued testing, but do not add the role interactions or H2H feature to production based on these experiments.

### Coach matchup probabilities

Coach win-probability predictions have a chronological model and audit, but the proposed Platt recalibration worsened Brier and log loss. Do not deploy the calibrator. Coach score projections still need to be evaluated with verified Dunkest credit/multiplier inputs before a coach-specific matchup change can be promoted.

## 4. Optimizer strategies: credits, roles, schedule and risk

Existing experiments compare expected-value vs risk-adjusted objectives, plusvalenza, rest/schedule, H2H and transfer-cost coefficients. The evidence is not strong enough to select a new production risk parameter:

- Rest/schedule challenger versus expanded matchup baseline: +1.56 proxy team points per round over 409 paired rounds, 95% interval [−1.95, +5.08]; inconclusive.
- Transfer-cost coefficient 2.5 versus 5.0: +0.32 proxy net points, 95% interval [−2.42, +3.01]; inconclusive. Coefficient 2.5 versus 0.0 was +2.66, 95% interval [+0.04, +5.31], but the candidate universe is restricted and all scenarios use the same fixed 5-point scoring malus. This does not validate changing the official transfer penalty.
- Frozen 2026/27 GW1 strategy variants were built from snapshots 149–151 hours before earliest tip-off, while the strict freshness limit is 36 hours. They validate the variant-generation pipeline only, not a decisive realized-score comparison.
- The production optimizer enforces credit budget, positional roster counts, player/team limits, captain/sixth-man/bench slots, coach budget/team rules, availability gates, and transfer malus. Existing lineup comparisons remain proxy results because authentic historical full-market rosters, coach prices, and fixture-linked coach/player outcomes are incomplete.

**Decision:** retain the current expected-value default and configured risk lambda. Do not pick the best risk lambda or lineup strategy from stale GW1 snapshots or incomplete historical candidate pools. For a promotion-grade comparison, freeze the complete market, injury, coach and fixture snapshots before lock; score all variants with the same verified realized scoring and transfer count; compare paired rounds with cluster-bootstrap intervals.

## 5. Verification and artifacts

- New uncertainty audit script: `scripts/audit_dunkest_uncertainty_expanding_oos_v1.py`.
- New uncertainty audit report/CSV/JSON: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2.*`.
- Existing ensemble search: `scripts/tune_dunkest_ensemble_weights_walk_forward_v1.py` and `reports/audit/dunkest_ensemble_weights_walk_forward_20261012T172631Z.md`.
- Existing model hyperparameter report: `reports/audit/dunkest_pdk_model_tuning_20261012_v1.md`.
- Existing matchup and lineup strategy evidence is cited above.
- No production settings or model artifacts were changed. Do not treat the 2025/26 results as a fresh untouched holdout; preserve a future season/round block for final evaluation.
