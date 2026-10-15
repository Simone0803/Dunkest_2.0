# Historical Dunkest backtest — corrected methodology and results

Generated (UTC): 2026-10-13T08:33:58.680179+00:00

## Corrected historical method

For a target round **r**, features and candidate prices are taken from each player's latest archived row strictly before r. The CR from the previous observed round is carried forward when the player did not appear in the immediately preceding round, since no new appearance is recorded from which a price change could be observed. Target-round PDK is used only to score the forecast/lineup after the round, never as a predictor.

The matchup date is inferred from high-confidence player/team/game links to the official-valid Dunkest game archive. Opponent defensive PTS/REB/AST features are computed from NBA team logs strictly before that date. The current target PDK is not passed into the feature matrix.

## Player score forecast

Walk-forward folds train on earlier valid seasons and test on 2022-23, 2023-24 and 2024-25. Across the three held-out seasons:

| Feature family | Mean fold MAE | Mean fold RMSE |
|---|---:|---:|
| Historical form only | 7.718 | 10.041 |
| Historical form + lagged CR | 7.521 | 9.824 |
| Historical form + lagged CR + current matchup context | 7.512 | 9.809 |
| Previous-five-round PDK mean | 8.002 | 10.507 |

Pooled out-of-fold MAE for the lagged-credit-plus-matchup model is **7.512 PDK**, compared with **8.002** for the previous-five-round baseline. Lagged CR improves the score model. The current opponent-defense encoding adds only a small incremental improvement over CR without matchup, so matchup modelling should be refined with position-specific defensive allowances, pace, minutes/role interaction and opponent-specific history rather than assumed to be solved.

## Coach outcome reconstruction

- NBA games paired from verified team logs: **9,519**.
- Overtime games inferred from team-game minutes: **502**.
- Mean fold MAE for the pregame team-form model's reconstructed neutral-credit coach base score: **16.073**.
- Mean fold MAE for the previous-ten-game base-score baseline: **16.596**.

The base score is reconstructed using the repository's coach rules and final NBA team points, margin, thresholds and overtime, with coach CR equal to opponent coach CR so the credit-difference coefficient is 1.0. This is useful for training and validating the match-outcome component, but it is **not exact historical credit-adjusted coach PDK** because historical coach prices are absent.

## Historical lineup experiment

This is an all-high-confidence-round proxy backtest for 2022-23 through 2024-25, using each player's latest known prior CR and the repository's roster optimizer. It evaluated **409 rounds**:

| Metric | Player model | Previous-five-round baseline |
|---|---:|---:|
| Mean realized lineup + neutral-credit coach base score | 160.88 | 140.34 |
| Difference | +20.54 | — |
| Median per-round difference | +17.66 | — |
| Rounds won head-to-head | 63.8% | — |

The average candidate pool contains **210 players**. It covers approximately **94.9%** of players listed in the target-round outcomes. This is substantially better than using only players from the immediately previous round, but it is not a complete archived pre-lock market.

The proxy comparison assumes coach CR = 10 for all teams and applies no transfer malus because historical carried rosters are not available. **Do not interpret the +20.54 as a certified real-world lineup gain.** It is evidence that the historical-form-plus-price model is promising under the stated assumptions; exact coach prices, complete roster universe and transfer policy remain unvalidated. The MILP was infeasible on 49 rounds and the candidate pool was too small on 6; those rounds are excluded from the lineup comparison.

## What this resolves—and what it does not

**Resolved:** historical player predictions can be evaluated chronologically using lagged CR and prior player form; matchup context can be reconstructed for high-confidence dates; coach base outcomes can be rebuilt from NBA results; and a broad lineup proxy comparison can be run without inventing pregame data.

**Still not certified:** exact historical coach price multipliers, historical transfers/malus, complete pre-lock player eligibility for players never observed earlier in the season, and any official claim about the best historical lineup strategy. Those require additional market archives or explicitly labelled assumptions.

Production model/configuration and the frozen prospective run remain unchanged.

## Reproducible artifacts

- Player score walk-forward: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v1.md`
- Coach base-score reconstruction: `reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1.md`
- Full proxy lineup backtest: `reports/audit/dunkest_historical_lineups_lagged_market_20261013_v5.md`
- Detailed JSON summary: `reports/audit/dunkest_historical_backtest_reframed_20261013_v1.json`
