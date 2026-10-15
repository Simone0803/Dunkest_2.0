# Dunkest post-match evaluation workflow — V1

## Purpose

Connect a frozen prediction run to verified realized outcomes without replacing pre-match data or silently guessing missing scores. The collector and evaluator use the run's archived NBA fixture IDs, player credits, coach credits, predictions and lineups.

## Current status

As of 12 October 2026, the archived GW1 fixtures begin on 20 October 2026. No post-match results for those fixtures can exist yet. The initial evaluation therefore returns not_ready; this is expected and does not indicate a model failure.

## After the full gameweek has finished

1. Refresh the official per-player Dunkest game history using the dedicated collector (it writes to a current-season-only path, separate from the 2018–25 historical archive):

       PYTHONPATH=src ./.venv/bin/python scripts/collect_dunkest_player_games_current_season_v1.py \
         --market data/predictions/20261012T171217Z_2f98f42b/pre_match_snapshot/player_credits_26_gw1.parquet

   Use the credits file from the exact frozen run being evaluated, not a later live market. By default, the collector refreshes all resolved player IDs on each invocation because the API returns season-to-date history; otherwise an earlier successful/empty response could miss games played later. Use `--resume` only to continue an interrupted collection when reusing existing successful responses is intentional; do not use it for post-match evaluation. A diagnostic `--limit N` run writes its checkpoint and audit but deliberately does not publish/overwrite the canonical normalized Parquet. Review data/raw/dunkest_player_games_current_2026-27_v1/player_id_resolution.csv before relying on it: the current Dunkest catalog may not uniquely identify every player name in the frozen roster. The collector leaves unmatched/ambiguous names unresolved rather than guessing. Once official games have completed, the normalized path is data/processed/official_dunkest_player_games_2026-27.parquet. Refresh the final NBA team boxscore log separately at data/processed/team_game_logs_2026-27.parquet or pass explicit paths to the builder.

2. Run the collector against the chosen frozen prediction run:

       cd /Users/simone/Documents/Dunkest
       PYTHONPATH=src ./.venv/bin/python scripts/build_dunkest_post_match_results_v1.py --run-id 20261012T171217Z_2f98f42b

   Replace the run ID with the prediction run you want to assess. The collector filters invalid Dunkest game rows, links player results by frozen roster identity + opponent + local game date, and computes coach points from final NBA team scores and the coach market archived before tipoff. It refuses to assign a result when the fixture mapping is absent or ambiguous.

3. The builder also reads `data/processed/player_game_logs_2026-27.parquet` (or `--player-logs`) to infer overtime from summed player minutes. Team-level logs often report `MIN=240` even for overtime, so the builder deliberately leaves coach scores unresolved when player-minute evidence is missing. It also validates that each coach/team/opponent tuple matches the archived fixture.

   The collector requires at least four hours after the latest mapped fixture kickoff before archiving. By default it archives only if all predicted player-fixture pairs and all frozen coach-fixture pairs have verified actuals. If some outcomes are unresolved, inspect the audit and missing-keys CSV; do not turn missing scores into zero. The `--allow-partial` flag is available for diagnostic archives, which will remain partial in evaluation.

4. Evaluate the immutable archive against the same run:

       PYTHONPATH=src ./.venv/bin/python scripts/evaluate_archived_run_post_match_v1.py --run-id 20261012T171217Z_2f98f42b

## Outputs

- reports/backtest/post_match_collection_audit_<run_id>.json: fixture, player-coverage, coach-coverage and timing checks.
- reports/backtest/post_match_collection_audit_<run_id>_missing.csv: expected player scores without a unique verified match, plus unresolved source records.
- data/archive/<season_id>/gw<gw>/post_match_<timestamp>_<id>/: immutable player/coach results plus source and SHA-256 manifest.
- reports/backtest/post_match_evaluation_<run_id>.json/.md: forecast MAE, RMSE, bias, interval coverage and realized lineup scores.
- reports/backtest/post_match_evaluation_<run_id>_lineups.csv: lineup-level completeness and realized scores.

## Canonical actual-result columns

Player result rows must include player_name, nba_game_id, actual_pdk. Coach rows must include coach, nba_game_id, actual_coach_pdk. The collector creates those columns from official source data. Missing player outcomes are not imputed; include an explicit zero only where the official result source confirms that the player had zero fantasy points for that fixture.

## Safeguards

- Every pre-match file listed by the run manifest is re-hashed before evaluation.
- The prediction run must precede the earliest fixture kickoff; the fixture mapping itself must have verified flags, source retrieval timestamps before tipoff and non-empty payload hashes.
- Post-match archive season and gameweek must match the prediction run; result files must match their recorded SHA-256 hashes.
- Conflicting duplicate player/fixture or coach/fixture scores, fixture IDs outside the archived mapping and premature post-match captures are rejected.
- Partial coverage is explicitly reported. No metric treats an unknown score as zero.
- The scripts only write new timestamped archive/report artifacts; they do not overwrite raw inputs, reset Git, or commit changes.
