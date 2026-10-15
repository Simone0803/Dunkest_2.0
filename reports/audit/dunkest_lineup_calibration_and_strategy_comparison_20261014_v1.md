# Dunkest lineup score reliability and calibrated strategy comparison

Generated: 2026-10-14

## Summary

The full-slate lineup backtest now has 458/464 rounds with feasible lineups. A zero-inclusive candidate-universe model and past-only role/history residual calibration were tested against a calibrated previous-five baseline.

## Findings

1. **Proxy result:** V7 model beats the calibrated baseline by +43.83 PDK per round (75.5% wins, 95% paired bootstrap CI [+38.61, +49.05], n=458).
2. **Improvement vs earlier model:** V7 model beats V6 raw model by +26.24 PDK per round (68.8% wins, 95% CI [+21.24, +31.28], n=458).
3. **Player forecast calibration:** model MAE 6.804 → 6.713 but RMSE 9.963 → 9.977; mixed effect. Baseline MAE 9.671 → 8.578 and RMSE 13.135 → 11.905.
4. **Post-selection score calibration:** model lineup-score MAE 43.83 → 43.37; baseline 111.64 → 52.66. The baseline's selected-lineup expected score is extremely optimistic before this correction.
5. **Strict actuals warning:** only 5 rounds overlap with complete observed scores for both V6 and V7 strategies. On those 5, V7 model averages 7.03 fewer points than the V7 baseline and wins 40%. This does not corroborate the proxy result and is far too small for a reliable conclusion.

## Why the proxy is not proof

The zero-inclusive strategy assumes a prior-observed player with no target-round row in the official weekly archive scores 0. This is plausible for non-appearance but cannot distinguish non-appearance from missing/incorrect roster identity. The candidate pool is reconstructed, CR/role are lagged, availability is not timestamped, coach credits and transfer malus are unknown, and lineups are independently optimized each round rather than managed sequentially.

## Decision

**Do not promote V7 to production.** Keep it as a challenger. The next work should target the five-round strict sample bottleneck: improve player identity/team linkage and determine whether absent weekly rows can be verified as zero through official game-level records. Continue prospective pre-lock snapshot capture so future rounds can be scored without proxy assumptions.

## Detailed reports

- `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7.md`
- `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_proxy_bootstrap.md`
- `reports/audit/dunkest_v6_v7_lineup_strategy_paired_bootstrap_20261014_v1.md`
- `reports/audit/dunkest_lineup_postselection_calibration_20261014_v1.md`
