# Dunkest autonomous code validation — 2026-10-14

## Production run

- Run: `data/predictions/20261014T100227Z_3022ad73/`
- Three roster candidates were produced and independently checked.
- Each roster has 10 unique players, respects the 95 CR budget, has one captain and one coach, and satisfies the per-turn lineup slot constraints.
- Expected team PDK: 220.88, 211.87, and 207.80. These are forecasts, not realized scores.
- All selected coach projections use `verified_matchup` source.
- The production training run used 18,141 official Dunkest PDK labels for the primary prior-season model.

## Lineup-browser fixes

- Per-turn market captures are merged into explicit `lineup_group_turn1`, `lineup_group_turn2`, and `lineup_group_turn3` fields instead of treating the latest scrape as the only rotation annotation.
- Starter caps are enforced after merging all scroll observations for a fixture. This prevents the starter counter from resetting on each viewport and promoting bench players to starters.
- Fallback matching for lineup labels is restricted to the two teams in the selected fixture; unavailable-player matching remains league-wide.
- A fixture-status conflict was detected for LAC: the latest browser style observation marked LAC ineligible, while the previous verified gameweek mapping marked LAC eligible. The current effective mapping retains the previous verified positive flag so the same 30-team slate is not reduced to 29 teams. The conflict is recorded in `data/lineups_fixtures_validation.json`; future raw per-turn observations are saved separately.

## Verification

- Full test suite: **299 passed** in 9.96 seconds.
- `git diff --check`: passed.
- Remaining warnings: 6,768 PuLP `LpVariable` deprecations, 31 `PULP_CBC_CMD` deprecations, and one expected test warning for a market fixture without freshness metadata.

## Multi-season training-window experiment

Script: `scripts/compare_dunkest_single_vs_multiseason_train_window_v1.py`
Report: `reports/audit/dunkest_single_vs_multiseason_train_window_20261014_v1.md`

The same ExtraTrees configuration and past-only feature adapter were evaluated with single-season versus expanding multi-season training on four forward season folds.

- Pooled player-game MAE: **7.5524** single-season vs **7.5365** multi-season.
- Paired MAE difference (multi minus single): **-0.0159**; 95% date-cluster bootstrap interval **[-0.0225, -0.0092]**.
- 2025/26 test fold, trained only on certified 2020/21–2024/25 labels: MAE **7.5504** single-season vs **7.5227** multi-season (18,412 test rows; 93,766 multi-season training rows).

This supports further multi-season integration, but the experiment is not a production-equivalent lineup backtest. The production primary trainer remains single-season for the season opener; no weights were changed on player-level MAE alone. A common production inference adapter and lineup-level out-of-sample validation remain required before promotion.

## Change management

No commit or push was performed. Existing unrelated working-tree edits were preserved.
