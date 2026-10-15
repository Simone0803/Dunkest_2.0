# Dunkest project follow-up — 2026-10-13 V17

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

Across 409 matched source-round/date slices from 2022/23–2024/25 (the original proxy labels these as rounds):

| Optimizer transfer-cost coefficient | Mean gross score | Mean official-net score | Mean transfers/slice |
|---:|---:|---:|---:|
| 0.0 | 159.856 | 108.218 | 10.328 |
| 2.5 | 157.652 | 110.879 | 9.355 |
| 5.0 | 155.262 | 110.556 | 8.941 |

A paired round bootstrap, stratified by season with 10,000 replicates, gives:
- Coefficient 2.5 vs 5.0: official-net delta **+0.323 points/slice**, 95% CI **[−2.425, +3.009]** — inconclusive.
- Coefficient 2.5 vs 0.0: official-net delta **+2.661 points/slice**, 95% CI **[+0.036, +5.313]** — small positive signal in this proxy.
- Coefficient 0.0 vs 5.0: official-net delta **−2.338 points/slice**, 95% CI **[−5.573, +0.798]** — inconclusive.

The same 49 date slices per scenario were infeasible, plus 6 slices had too few candidates; paired analysis uses only rounds valid in all three scenarios. Candidate coverage remains restricted: only about 60.5% of the prior-observed candidate pool had a target-round outcome row, while about 94.9% of target player rows were present in the candidate pool on average. Missing target rows are treated as zero within the proxy.

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

## 5. Infeasible lineup diagnosis: restricted candidate pool, not a production MILP defect

I reproduced the 2022-12-13 failed slice (season ID 9, source round index 54) and ran controlled feasibility relaxations without modifying the production optimizer. Raising the budget to 200 credits and removing the minutes thresholds did **not** make the lineup feasible; changing the same-team cap from 3 to 4 did. This isolates the failure to the team-capacity constraint in the candidate pool, not to budget or minutes eligibility.

A new audit then checked all failures in the sequential transfer proxy:

- 147 failed rows in the experiment CSV collapse to **49 unique failed date slices** (each repeated across the three transfer-cost scenarios).
- In **all 49/49**, the target-date matchup join left candidates from only **1–3 NBA teams**, while the pregame coach source had 4–26 teams for those dates (mean 13.14). Under the unchanged max-three-per-NBA-team rule, even allowing the coach to come from a different team, the upper bound was only **3–9 player slots**, below the required 10; the shortfall was 1–7 slots.
- Example: on 2022-12-13, the proxy had 43 candidates but only GSW, LAL and UTA in its matchup-eligible pool (maximum capacity: nine players). The pregame coach source listed ten teams for that date, including opponents MIL, BOS and NOP. The feature/matchup join therefore did not expose the full slate to the optimizer.

**Interpretation:** CBC is correctly reporting infeasibility for the supplied restricted pool. Do not relax the Dunkest three-per-team rule or change production MILP constraints. The historical lineup proxy's candidate universe is incomplete, and the transfer-coefficient comparison is more fragile than previously indicated: its small 2.5-vs-5 signal is exploratory only and must not be used to tune production. The production transfer coefficient remains 5.

The next valid lineup experiment requires a candidate universe and role/team identity for the full pre-lock market, plus historical CR and explicit outcomes at the relevant scoring/turn granularity. Missing players cannot safely be filled in by assuming that an absent target row means zero points. Until those inputs are recovered, prioritize player-level walk-forward validation and retain lineup results as restricted sensitivity analyses.

Artifacts:
- `scripts/audit_dunkest_historical_lineup_infeasibility_v1.py`
- `reports/audit/dunkest_historical_lineup_infeasibility_20261013_v1.md` and `_rounds.csv` / `.json`
- `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2.md` remains the original experiment report; its transfer comparison should be read with this additional limitation.

## 6. Historical round-to-game mapping: full boxscore signature audit

To investigate the candidate-universe gap without trusting repeated PDK values alone, I added a read-only linkage audit matching historical `tot` rows to the official per-player game archive on season, canonical player identity, NBA team, PDK rounded to two decimals, and 17 boxscore fields. Only rows with `gp=1` are eligible for single-game linkage.

- **93,779** rows audited; **85,477 (91.1%)** have a unique full-signature match, **410** have ambiguous signatures, and **7,892** have no exact signature match.
- Across **779** source week-rounds, the uniquely linked rows point to one NBA date in **773** rounds and multiple dates in 6. Median unique-signature coverage per round is **89.5%**; median mapped team count is 12.
- Example: season ID 9, week 22, round 3 (13 December 2022) has 23 source rows, 19 unique full-signature matches, and 4 unmatched rows. The source table lists GSW, LAL, MIN and UTA; the exact game-signature matches for that round/date cover only GSW and UTA. A PDK-only date join can therefore pull in a team from a row that does not match the target-date boxscore.

**Decision:** the historical weekly tables can corroborate many realized player-game outcomes and approximate round dates, but they are not a complete pre-lock candidate market. The unmatched rows remain unresolved and must not be automatically dropped, imputed as zero, or relabelled. The full-signature audit improves linkage evidence but does not recover historical prices/availability or prove the official semantics of every validity flag.

Artifacts:
- `scripts/audit_dunkest_historical_round_game_mapping_v1.py`
- `reports/audit/dunkest_historical_round_game_mapping_20261013_v1.md`
- `reports/audit/dunkest_historical_round_game_mapping_20261013_v1_rounds.csv`
- `reports/audit/dunkest_historical_round_game_mapping_20261013_v1_rows.csv`
- `reports/audit/dunkest_historical_round_game_mapping_20261013_v1.json`

## 7. Unmatched rows: the dominant cause is historical team-code mismatch

The follow-up diagnostic tested the 7,892 rows that failed the strict season + player + team + PDK + 17-stat linkage. For this test, I deliberately removed only the source team field from the matching key while still requiring the same season, canonical player, PDK rounded to two decimals, and all 17 boxscore statistics to match an official NBA player-game row.

- **7,873 / 7,892 (99.76%)** have an exact player + PDK + 17-stat match in the official archive when the source team field is ignored.
- For all **7,873**, the source row's team code differs from the NBA team attached to that exact official game row.
- The remaining **19** rows have no exact 17-stat signature even when team and PDK are ignored. They cluster in season ID 5, source week 43 round 2 (16 rows) and week 53 round 2 (3 rows), suggesting a localized archive/round discrepancy rather than a broad identity issue.

Examples in season ID 13, source week 10 round 1 (NBA date 2023-11-18): the source table assigns Vasilije Micic to CHA, Cameron Payne to PHI, and Seth Curry to CHA, while the exact official game signatures point to OKC, MIL, and DAL respectively. The PDK and all 17 boxscore fields match. This is strong evidence that team_code in the weekly table is not reliably the player's NBA team at the historical game date; it may reflect a later/current roster association or another Dunkest-side assignment. The exact upstream semantics are not yet proven.

**Decision:** do not rewrite the source team field globally. Preserve its original value and semantics. For historical matchup features, use the official game-date NBA team from the linked game record; retain the source Dunkest team assignment separately if needed. This distinction must be explicit in any future training/backtest dataset. The 19 residual rows are examined separately in Section 8 below and remain unresolved pending upstream provenance.

Artifacts:
- scripts/audit_dunkest_historical_round_game_unmatched_v3.py
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3.md
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rows.csv
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_seasons.csv
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rounds.csv
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3.json

## 8. Residual 19 rows: likely row-level outcome mismatch, not just team identity

A focused comparison of the 19 residual rows found that only **7** have the same player-season PDK value somewhere in the official archive; **12** do not. Even where a PDK value recurs, it belongs to another candidate date and does not establish a game link. Comparing the source boxscore against every official game for the same player in that season, the nearest official row still differs in **4–12 of the 17 statistics**.

The residuals are concentrated in season ID 5, source week 43 round 2 (16 rows) and week 53 round 2 (3 rows). This is stronger evidence of a localized source/round row inconsistency than a simple team-code mismatch. Do not use these 19 rows as exact game outcomes until their upstream provenance is established; do not infer zeros, DNP, or ineligibility.

Artifacts:
- scripts/audit_dunkest_historical_round_game_residuals_v1.py
- reports/audit/dunkest_historical_round_game_residuals_20261013_v1.md
- reports/audit/dunkest_historical_round_game_residuals_20261013_v1.csv
- reports/audit/dunkest_historical_round_game_residuals_20261013_v1.json

## 9. Prospective holdout and leakage discipline

The 2026/27 GW1 run remains frozen until **2026-10-23 12:00 UTC**. Do not inspect it for tuning before cutoff, and do not tune on the holdout after evaluation. Historical walk-forward folds remain the venue for development.

## Verification

- Full test suite: **276 passed**, 6,800 warnings in 6.74 seconds.
- Python compilation passed for the four linkage/residual audit scripts; `git diff --check` passed.
- Full-signature unmatched-row follow-up: **7,873 of 7,892** strict-signature failures are exact player/PDK/boxscore matches once source team is excluded; all 7,873 disagree on team code.
- The residual 19 rows are isolated to two late season-ID-5 source rounds for targeted review.
- No source data, production code/config, official labels, temporal split, or frozen holdout was changed.
- No commit or push performed; existing working-tree changes preserved.
