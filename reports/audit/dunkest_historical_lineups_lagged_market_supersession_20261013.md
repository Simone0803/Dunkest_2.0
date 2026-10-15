# Historical lineup market backtest artifact status

This note prevents earlier diagnostic runs from being misread as the final comparison.

- `dunkest_historical_lineups_lagged_market_20261013_v1.*`: superseded; its player outcome join used inconsistent identity normalization and realized outcome coverage was invalid.
- `dunkest_historical_lineups_lagged_market_20261013_v2.*`: superseded; it only used players who appeared in the immediately previous round, which covered too little of the target round's player universe.
- `dunkest_historical_lineups_lagged_market_20261013_v4.*`: valid sampled diagnostic (every third round), superseded by the all-high-confidence-round V5 run.
- `dunkest_historical_lineups_lagged_market_20261013_v5.*`: current reference proxy comparison. It carries forward each player's latest prior observed CR and evaluates 409 rounds across 2022-23 through 2024-25. It is still not an exact historical market backtest because coach CRs, transfer carry-over and full pre-lock roster snapshots are absent.

Use `reports/audit/dunkest_historical_backtest_reframed_20261013_v1.md` as the consolidated interpretation. None of these experiments modified the production model or configuration.
