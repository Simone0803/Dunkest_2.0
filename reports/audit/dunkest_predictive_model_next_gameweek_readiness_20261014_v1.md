# Predictive model and next-gameweek workflow — 2026-10-14 V1

## Priority

The immediate objective is prediction quality and a working forward workflow, not declaring a historical lineup strategy winner. Full lineup-realized validation is deferred until the season supplies real prospective outcomes. Player-level walk-forward checks and strict temporal-leakage safeguards remain useful for improving the predictor. The 2026/27 GW1 holdout stays frozen until 2026-10-23 12:00 UTC.

## Implemented in this pass

- Normal `dunkest run` now treats `--turno` as the starting Lineups tab for acquisition, captures all three turns, merges the per-turn lineup annotations, and optimizes the complete gameweek instead of filtering the MILP to one turn.
- A freshly captured gameweek fixture bridge is matched to NBA game IDs by the displayed date and team pair, checks timestamp freshness and eligibility, and is merged into the season mapping without deleting prior gameweeks. A missing or unverified mapping stops prediction rather than inventing an opponent/turn.
- The prediction pipeline attaches each candidate's verified opponent, NBA game ID, Dunkest turn, and turn-specific lineup/availability annotation. Non-score-bearing teams are excluded; forecast opponent fields are overridden with the upcoming verified matchup rather than the last historical opponent.
- Current roster input is required from GW2 onward: exactly ten distinct normalized player identities plus a nonblank coach. The MILP compares that roster with each proposed lineup and applies the configured transfer malus, including coach changes.
- The README now gives a valid command including `--turno 1` and explains that it starts a complete three-turn capture. `--no-lineups-scrape` requires an already verified mapping for the requested gameweek.
- The primary model now keeps the certified multi-season Dunkest PDK training source beyond GW1. For subsequent gameweeks it may append only completed current-season rows with official Dunkest PDK labels; proxy labels, inference rows, and the 2025/26 holdout are excluded. Current-season labels receive neutral sample weight until enough data accumulates.

## Validation performed

- Full test suite: **395 passed** with `-W error::DeprecationWarning`.
- Focused workflow/fixture/training tests cover multi-gameweek mapping retention, verified matchup/turn assignment, turn-specific lineup labels, fail-closed behavior when fixtures are absent, and exclusion of proxy/inference/holdout rows from current-season training.
- Executed the production multi-season training function against the local certified archive: **93,766 rows**, **24 usable features**, seasons 2020/21–2024/25, absolute official-PDK target; current-season official rows appended: **0** (expected before the 2026/27 regular season has started). Training completed in 88.3 seconds.
- `py_compile` and `git diff --check` passed.
- No live scrape or next-gameweek prediction was run: the current Lineups view and official results for GW2 are not yet available as a genuine post-GW1 workflow test. The actual capture path will be exercised when the next target gameweek is displayed.
- No commit or push performed.

## Next modeling priorities

1. Once GW1 is complete, inspect the official PDK labels available to the trainer and verify that current-season official rows are appended with the correct game dates and no same-game leakage.
2. Continue improving player forecasts on player-level walk-forward metrics (MAE/RMSE/bias and high-score/rookie cohorts), without using lineup realized scores to tune before the holdout cutoff.
3. Inspect the generated lineup's expected score, uncertainty, role/turn assignments, captain, coach and transfer accounting as prediction diagnostics—not as proof of realized performance.
4. When GW2 becomes the active Lineups slate, run the complete workflow with the actual current roster and confirm the new fixture mapping is persisted alongside GW1.

## Command after GW1

Copy `config/roster.example.yaml` to `config/current_roster.yaml`, enter the ten players and current coach, then run:

```bash
./.venv/bin/python -m dunkest run --giornata 2 --turno 1 --roster config/current_roster.yaml
```

The command will refresh all three Lineups turns, merge their annotations, validate the target gameweek mapping, train on certified historical labels plus any available current-season official labels, and optimize three distinct candidate rosters under the current transfer penalty. It fails closed if fixture evidence or the current roster is incomplete.
