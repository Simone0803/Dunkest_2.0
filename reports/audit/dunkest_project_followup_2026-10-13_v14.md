# Dunkest project follow-up — 2026-10-13 V14

## Scope

This iteration pursued alternative empirical proxies for the missing historical participation labels and transfer/roster state. Production predictors, weights, settings, and the frozen prospective 2026/27 GW1 holdout were not changed.

## 1. Participation: label audit and proxy limits

I tested two walk-forward formulations rather than assuming missing NBA player-game rows are DNP/OUT labels.

- **V2 (128,483 candidate-game observations)** treated a missing target player-game row as a proxy non-appearance. Its Brier/AUC looked better than simple recent-rate baselines, but this target mixes actual non-appearances with trades, roster changes and source omissions. Those metrics are not reliable evidence of calibrated Dunkest participation probability.
- **V3 (96,515 observations)** excludes missing target rows from both training and evaluation. The remaining target rows are positive-minute appearances in **99.64%–99.79%** of cases across the four test seasons. The archive therefore contains almost no explicit negative participation labels; the apparent discrimination is largely a consequence of which players enter the box-score archive.

**Decision:** no production participation model. V2 is a useful sensitivity analysis only; V3 exposes the selection bias and label shortage. A valid p_play model needs a candidate universe assembled before lock and explicit outcomes for every candidate, including DNP/OUT and players absent from the NBA box-score feed. This does not block using historical minutes/score distributions to model expected fantasy points conditional on playing.

Artifacts:
- `scripts/audit_dunkest_nba_appearance_probability_proxy_walk_forward_v2.py` and `reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v2.md` (missing rows treated as proxy negatives; superseded for label interpretation)
- `scripts/audit_dunkest_nba_appearance_probability_proxy_walk_forward_v3.py` and `reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v3.md` (missing rows excluded; demonstrates near-absence of negative labels)
- Both versions include metrics/predictions CSV and audit JSON.

## 2. Transfer malus: sequential walk-forward optimization

I extended the ex-post sensitivity into a chronological optimizer simulation. For every round, the optimizer selects a new lineup using only lagged player features and pregame coach forecasts. Each scenario carries forward its own previous proxy roster and coach, then scores the selected lineup after selection. The optimizer coefficient varies across 0, 2.5 and 5 points per transfer, but **every scenario is scored under the same fixed 5-point transfer malus**. This avoids confusing a tuning coefficient with the official scoring rule.

Across 409 matched rounds from 2022/23–2024/25:

| Optimizer transfer-cost coefficient | Mean gross score | Mean official-net score | Mean transfers/round |
|---:|---:|---:|---:|
| 0.0 | 159.856 | 108.218 | 10.328 |
| 2.5 | 157.652 | 110.879 | 9.355 |
| 5.0 | 155.262 | 110.556 | 8.941 |

A paired round bootstrap, stratified by season with 10,000 replicates, gives:
- Coefficient 2.5 vs 5.0: official-net delta **+0.323 points/round**, 95% CI **[−2.425, +3.009]** — inconclusive.
- Coefficient 2.5 vs 0.0: official-net delta **+2.661 points/round**, 95% CI **[+0.036, +5.313]** — small positive signal in this proxy.
- Coefficient 0.0 vs 5.0: official-net delta **−2.338 points/round**, 95% CI **[−5.573, +0.798]** — inconclusive.

The same 49 rounds per scenario were infeasible, plus 6 rounds had too few candidates; paired analysis uses only rounds valid in all three scenarios. Candidate coverage remains restricted: only about 60.5% of the prior-observed candidate pool had a target-round outcome row, while about 94.9% of target player rows were present in the candidate pool on average. Missing target rows are treated as zero within the proxy.

**Decision:** no change to production's 5-point transfer coefficient. The apparent 2.5-point coefficient advantage over 5 is tiny and statistically inconclusive; roster carry-forward is simulated rather than actual, and complete market/coach-price data are unavailable. Treat 2.5 as a candidate for further validation, not as a replacement. The initial sequential V1 artifact is retained for reproducibility but superseded for penalty comparisons by V2, which applies the same official 5-point scoring malus to every scenario.

Artifacts:
- `scripts/backtest_dunkest_historical_lineups_sequential_transfer_v2.py`
- `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2.md`
- `scripts/audit_dunkest_historical_lineups_sequential_transfer_paired_bootstrap_v1.py`
- `reports/audit/dunkest_historical_lineups_sequential_transfer_paired_bootstrap_20261013_v1.md`
- `scripts/audit_dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_v1.py` (earlier ex-post sensitivity)

## 3. Coaches: use the strongest available rule-aware forecast, quantify price uncertainty

The existing V3 coach Monte Carlo walk-forward audit evaluates 9,840 team-game outcomes across 2022/23–2025/26. It forecasts neutral-credit base coach score with MAE 15.184, compared with 16.073 for the direct model and 16.596 for the previous-ten baseline. On the 2025/26 holdout, its MAE is 15.051.

This is the best supported alternative for forecasting the **base coach score**. Official Dunkest coefficients can then be applied deterministically, and scenario analyses can quantify how coach price differences affect results.

**Decision:** retain the rule-aware Monte Carlo forecast; do not claim exact historical coach PDK. The missing historical coach CR at lock still prevents exact price-adjusted reconstruction. Scenario price differences remain sensitivity analyses, not observed historical prices.

Reference: `reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v3.md` and `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v3.md`.

## 4. Lineups and score-model changes

- Rest/schedule features improve player-level OOF MAE from 7.50275 to 7.47766, but the restricted lineup proxy does not show a robust gain (paired bootstrap interval for lineup-score delta crosses zero). Do not promote V6.
- Official PDK-history features improve MAE by only about 0.00315 on 2021/22–2024/25; the date-cluster interval includes zero. Keep experimental.
- H2H remains unpromoted at lineup level; role-conditioned matchup interactions remain unpromoted.
- Rookie prior cap remains unchanged.
- Historical lineup outputs remain restricted-universe proxies, not complete pre-lock market backtests. Their coach CR, carried roster, and transfer-state assumptions remain explicit.

## 5. Prospective holdout and leakage discipline

The 2026/27 GW1 run remains frozen until **2026-10-23 12:00 UTC**. Do not inspect it for tuning before cutoff, and do not tune on the holdout after evaluation. Historical walk-forward folds remain the venue for development.

## Verification

- Test suite: **276 passed**, 6,800 warnings in 6.36 seconds. Warnings are mainly PuLP deprecations and one freshness-metadata test warning.
- New participation, sequential-transfer and paired-bootstrap scripts compile; experiment artifacts were generated successfully.
- `git diff --check` passed.
- Production model/configuration unchanged.
- No commit or push performed; pre-existing working-tree changes preserved.
