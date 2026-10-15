# Dunkest project follow-up — 2026-10-13 (v26)

## 22. High-score tail and past-only residual correction

Added and executed the exploratory experiment:
- `scripts/experiment_dunkest_past_only_residual_correction_v1.py`
- `reports/audit/dunkest_20261013_past_only_residual_correction_v1.md`
- companion metrics, prediction and JSON audit files in `reports/audit/`.

The experiment starts from saved expanding-origin OOF predictions for the V6 rest/schedule model. It trains a second-stage residual model only on earlier-season OOF errors: 2023/24 is fitted from 2022/23; 2024/25 is fitted from 2022/23 and 2023/24. No 2025/26 or frozen 2026/27 predictions are loaded.

### Results

| Correction | 2023/24 MAE | 2024/25 MAE | Date-cluster 95% CI for ΔMAE in 2023/24 | Date-cluster 95% CI for ΔMAE in 2024/25 |
|---|---:|---:|---:|---:|
| Raw V6 prediction | 7.46376 | 7.46322 | — | — |
| Ridge residual | 7.48407 | 7.46852 | [+0.00824, +0.03163] | [−0.00544, +0.01583] |
| HistGradientBoosting residual | 7.45159 | 7.46267 | [−0.01889, −0.00511] | [−0.01178, +0.01088] |
| Extra Trees residual | 7.45464 | 7.45330 | [−0.01567, −0.00243] | [−0.02115, +0.00138] |

Negative ΔMAE means the corrected predictions improve. The high-score segment is where the hypothesis is most relevant: for actual PDK ≥25, raw MAE was 12.879 in 2023/24 and 12.553 in 2024/25. Extra Trees residual correction worsened that segment in 2023/24 (MAE 13.028) but improved it in 2024/25 (11.956). HistGradientBoosting showed a similar lack of stability: slightly worse on the actual ≥25 segment in 2023/24 (12.935) and better in 2024/25 (11.989). For actual PDK ≥30, both tree corrections improved the 2024/25 segment, but worsened it in 2023/24.

### Decision

**Do not promote the correction to production.** The correction has some promising season-specific signal, especially in 2024/25 high scores, but its effect is not stable across seasons. The paired bootstrap intervals also include zero for the 2024/25 overall comparison. This supports further model work rather than a production change.

The next model-focused step should be to separate expected opportunity from conversion: build past-only forecasts for minutes/role and usage/box-score rates, then combine those forecasts into a PDK expectation. A residual model based only on existing aggregate prediction, lagged CR and opponent summaries is not enough to consistently recover the high-score tail. Any such feature construction must use only information available before the target game and must not infer non-appearance from missing historical rows.

## 23. Verification and safety

- Script compiles and ran successfully; `git diff --check` passed.
- Three methods were evaluated on two expanding-origin validation seasons; target 2025/26 was not loaded.
- No production source, configuration, model artifact, ensemble weights, or frozen prospective GW1 snapshot was modified.
- No commit or push was performed.


## 24. Root-cause experiment: minutes × production rate

Added and executed `scripts/experiment_dunkest_minutes_rate_decomposition_v1.py`, with artifacts:
- `reports/audit/dunkest_20261013_minutes_rate_decomposition_v1.md`
- companion metrics, predictions, and audit JSON.

The experiment linked verified 2020/21–2024/25 Dunkest player-game targets to the historical NBA game crosswalk for target minutes. Current-game minutes/statistics are labels only. Predictors use past PDK, prior box-score lags/rolling summaries, rest, and opponent/home-away information. Expanding-origin folds are 2022/23, 2023/24, and 2024/25; 2025/26 and the frozen 2026/27 GW1 run were not loaded.

Data checks: 93,753 target rows have an unambiguous target-minute link; zero lag-1 PDK mismatches; zero conflicting duplicate labels. The three validation folds have 57,682 common predictions.

| Candidate | Pooled MAE | Pooled RMSE | MAE when actual PDK ≥25 | MAE when actual PDK ≥30 |
|---|---:|---:|---:|---:|
| Direct Extra Trees | 7.5658 | **9.8390** | 12.2917 | 14.3116 |
| Direct HistGradientBoosting | 7.5723 | **9.8306** | **12.0274** | **13.9093** |
| Minutes HGB × rate Extra Trees | **7.5556** | 9.8658 | 12.5222 | 14.5320 |

The best component product reduces pooled MAE by only ~0.010 PDK relative to the direct MAE winner, while increasing RMSE and worsening both high-score segments. Its fold effect is not stable: vs direct Extra Trees, ΔMAE was +0.0345 in 2022/23 (date-cluster 95% CI [+0.0117,+0.0584]), −0.0174 in 2023/24 (CI [−0.0406,+0.0034]), and −0.0469 in 2024/25 (CI [−0.0667,−0.0281]). **No production promotion.** Minute prediction itself reaches MAE 4.85–5.11 minutes across folds, but this is conditional on an observed, linked target game and does not model participation probability.

## 25. Conditional high-score mixture

Added and executed `scripts/experiment_dunkest_conditional_tail_model_v1.py` (balanced-weight attempt) and `scripts/experiment_dunkest_conditional_tail_model_v2.py` (unweighted, natural-prevalence probabilities), plus `scripts/audit_dunkest_conditional_tail_paired_bootstrap_v1.py`.

The balanced classifier overestimated high-score probabilities substantially (mean predicted P(PDK≥25) about 0.41–0.43 vs prevalence 0.225–0.231), causing overall MAE 8.532; it is rejected. The unweighted V2 mixture is much better calibrated at the aggregate level:
- For PDK ≥25, observed prevalence 22.5–23.1%, mean predicted probability 22.9%, Brier 0.123–0.124, ROC AUC 0.840–0.849.
- For PDK ≥30, observed prevalence 14.9–15.7%, mean predicted probability 15.1–15.8%, Brier 0.094–0.096, ROC AUC 0.853–0.859.

Pooled comparison for the ≥25 mixture: MAE 7.5633, RMSE 9.8308, actual-≥25 segment MAE 12.0441, and actual-≥30 segment MAE 13.9793. Paired date-cluster bootstrap, 3,000 replicates, stratified by season:
- Versus direct Extra Trees, overall ΔMAE −0.00247 (95% CI [−0.01345,+0.00884], inconclusive); actual ≥25 ΔMAE −0.24762 (CI [−0.28042,−0.21296]); actual ≥30 ΔMAE −0.33231 (CI [−0.37187,−0.28922]).
- Versus direct HistGradientBoosting, overall ΔMAE −0.00898 (CI [−0.01761,−0.00021]); actual ≥25 ΔMAE +0.01671 (CI [−0.00812,+0.04253], inconclusive); actual ≥30 ΔMAE +0.07000 (CI [+0.03712,+0.10237], significantly worse).

The mixture offers a tail improvement against Extra Trees but does not beat direct HistGradientBoosting on the ≥30 tail and trades a small MAE gain for essentially unchanged/worse RMSE. **Do not promote**. Tail probability can remain a research-side upside/risk signal, but lineup-level utility must be proven before it can influence selection.

## 26. Rookie/low-history decision

The prior rookie cohort audit (`dunkest_rookie_pdk_walk_forward_20261012_v1.md`) already shows a Random Forest walk-forward MAE of 6.431 vs 6.714 for the previous-10 baseline over 7,219 rookie rows, with first-three-game MAE 4.887 vs 6.773. The no-prior-official-PDK segment is only 210 rows and remains conditional on an official target existing. The college PDK/minute prior's temporal MAE was 0.110 vs 0.124 historical rookie-rate baseline; conditional rookie minutes MAE was 5.84 vs 7.35 minutes. The college minutes blend remains capped at 15% because these minutes labels are conditional on observed NBA participation. No rookie prior/weight change is justified by the new experiment, and no missing player-game row is interpreted as a zero or DNP.

## 27. Lineup-level gate and current decision

No new lineup-level claim is made. The historical lineup proxy remains constrained by incomplete round player pools and missing trustworthy pre-lock snapshots of credits, injury status, coach market, and fixture mapping; prior audits found many infeasible rounds because only 1–3 teams were represented in the candidate pool. A score-level improvement alone is insufficient to change lineup optimization, coach coefficients, or transfer malus. Keep production transfer malus 5 and the current solver/config unchanged until a complete, historically faithful lineup replay is possible.

## 28. Verification and safety

- New research scripts: `experiment_dunkest_minutes_rate_decomposition_v1.py`, `experiment_dunkest_conditional_tail_model_v1.py`, `experiment_dunkest_conditional_tail_model_v2.py`, `audit_dunkest_conditional_tail_paired_bootstrap_v1.py`, `experiment_dunkest_conditional_tail_blend_v1.py`.
- Scripts compile; `git diff --check` passes.
- Full test suite: `PYTHONPATH=src .venv/bin/python -m pytest -q` → **276 passed**, 6,800 existing warnings (primarily PuLP deprecations). Running pytest without `PYTHONPATH=src` failed collection because the local editable package is not visible to that invocation; with the source path explicitly set, the complete suite passes.
- All new model selection/validation used only target seasons through 2024/25. No 2025/26 target or frozen 2026/27 GW1 snapshot was loaded.
- No production source, config, model artifact, weights, or prospective snapshot was modified. No commit or push.
- Remaining material blocker: lineup-level backtest quality cannot be established until a complete historical candidate universe and reliable pre-lock snapshots are recovered.


## 29. Candidate ensemble blend

Because the unweighted threshold-25 mixture produced well-calibrated tail probabilities but was weaker than direct HGB on the ≥30 subgroup, I evaluated convex blends from saved predictions in `scripts/experiment_dunkest_conditional_tail_blend_v1.py`.

The most balanced tested candidate is 25% threshold-25 mixture + 75% direct HGB:

| Metric | Direct HGB | 25% mixture blend | Change |
|---|---:|---:|---:|
| Pooled MAE | 7.57227 | **7.56220** | −0.01007 |
| Pooled RMSE | 9.83061 | **9.81904** | −0.01157 |
| MAE, actual PDK ≥25 | 12.02739 | **12.01888** | −0.00851 |
| MAE, actual PDK ≥30 | 13.90934 | 13.91398 | +0.00465 |

The 3,000-replicate season-stratified date-cluster bootstrap for blend minus direct HGB gives:
- Overall ΔMAE −0.01007, 95% CI [−0.01235, −0.00784].
- Actual PDK ≥25 ΔMAE −0.00851, 95% CI [−0.01476, −0.00251].
- Actual PDK ≥30 ΔMAE +0.00465, 95% CI [−0.00344, +0.01323], inconclusive.

MAE and RMSE improve in each validation season (2022/23, 2023/24, 2024/25), and the ≥25 subgroup improves slightly in each fold. The ≥30 subgroup is mixed by season but the pooled CI does not show a reliable degradation. This is the strongest player-level candidate found in this phase. However, the gains are small in absolute PDK, the blend weight was selected on these validation folds, and lineup-level utility cannot yet be measured credibly with the available historical player pools/snapshots. **Keep it research-only; do not change production blend weights or optimizer behavior.**

Artifacts: `reports/audit/dunkest_20261013_conditional_tail_blend_v1.md`, metrics CSV, predictions CSV, and audit JSON.
