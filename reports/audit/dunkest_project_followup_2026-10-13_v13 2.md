# Dunkest project follow-up — 2026-10-13 V13

## Scope

This iteration pursued alternative empirical proxies for the missing historical participation labels and transfer/roster state. Production predictors, weights, settings, and the frozen prospective 2026/27 GW1 holdout were not changed.

## 1. Participation: train a narrower NBA appearance-continuity proxy

Because the archives do not include a complete pre-lock Dunkest candidate universe or explicit DNP/OUT labels, the new experiment predicts a narrower target: whether a player with a recorded appearance for the same NBA team in the previous five team games appears with positive minutes in the next team game.

Expanding-origin tests cover 2021/22–2024/25, with only earlier seasons used for each fold. 128,483 candidate-game observations were scored in the corrected V2 run (V1 is retained for reproducibility but superseded because its recent-appearance count included rare zero-minute rows).

Pooled row-weighted results:

| Method | Brier (lower is better) | Log loss (lower is better) | ROC AUC |
|---|---:|---:|---:|
| Logistic model with lagged history | 0.1334 | 0.4213 | 0.8331 |
| Previous-five appearance rate | 0.1527 | 0.7762 | 0.7885 |
| Previous-ten appearance rate | 0.1650 | 0.6921 | 0.7680 |
| Constant 90% probability | 0.2107 | 0.6567 | 0.5000 |

The lagged logistic proxy improves Brier score and ROC AUC in every test season versus the simple recent-rate baselines. This is evidence that a model can estimate continuity risk from historical logs.

**Decision:** keep it experimental and separate from production Dunkest p_play. The cohort is inferred from prior appearances, and a missing NBA row can mean injury, DNP, a roster move, or a source gap. These are not verified DNP/OUT labels, and the model is not a probability of availability across a Dunkest round.

Artifacts:
- `scripts/audit_dunkest_nba_appearance_probability_proxy_walk_forward_v2.py`
- `reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v2.md`
- Metrics and predictions CSV plus audit JSON with cohort/label provenance.

## 2. Transfer malus: ex-post switch-value sensitivity

A new proxy compares the independently optimized lineup for each round with the previous round's proxy lineup carried forward. It values each roster with current-round raw player PDK plus the neutral-credit coach base score, then subtracts 0, 1, 2, 3.5, or 5 points per estimated transfer. The transfer count is the number of new players plus one if the coach changes.

Across 229 sequential transitions in the 2022/23–2024/25 proxy:
- Mean gross gain from switching to the fresh recommendation: about 84.9 points before transfer costs.
- Mean estimated transfers per transition: about 9.7, including coach changes.
- At a 5-point penalty, the fresh recommendation still had positive ex-post net gain in about 69.9% of transitions pooled across both lineup variants.

These values are deliberately treated as **stress-test diagnostics, not an estimate of the optimal official transfer penalty**. The fresh lineup was not re-optimized under each penalty, the archived previous lineup is only a proxy for the user's carried roster, player slot/captain multipliers are not reconstructed for the retained roster, and missing target rows can affect realized totals. The very high turnover rate also reflects independently optimizing each round from scratch.

**Decision:** no change to the production transfer penalty. The next useful step is to make the optimizer's existing transfer logic run sequentially in a walk-forward simulation with a carried roster per penalty scenario, while reporting candidate coverage and uncertainty.

Artifacts:
- `scripts/audit_dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_v1.py`
- `reports/audit/dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_20261013_v1.md`
- Transition-level and metric CSVs plus audit JSON.

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

- Test suite: **276 passed**, 6,800 warnings in 6.46 seconds. Warnings are mainly PuLP deprecations and one test fixture freshness-metadata warning.
- The new experiment scripts compile; the corrected V2 participation run and the transfer-malus sensitivity artifacts were generated successfully.
- Production model/configuration unchanged.
- No commit or push performed; pre-existing working-tree changes preserved.
