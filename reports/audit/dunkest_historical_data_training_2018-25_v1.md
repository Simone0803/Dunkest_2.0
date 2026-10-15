# Dunkest historical data collection and PDK model experiment (2018/19–2024/25)

Date: 2026-10-11
Status: data collection complete; walk-forward experiment complete; model is **not integrated into production**.

## 1. Source and coverage

Sources used:
- Dunkest weekly statistics table: `https://www.dunkest.com/api/stats/table` and `/api/stats/dunkest/week/rounds`.
- Dunkest player-game history: `https://www.dunkest.com/api/player/games?player_id=…&season_id=…`.
- Dunkest public NBA player catalogue: `https://www.dunkest.com/it/nba/giocatori`.
- NBA player regular-season logs via `nba_api` LeagueGameLog.

The season IDs mapped from Dunkest's selector and data are:

| Season | Dunkest season ID | Weekly table | Official player-game rows after de-dup | Players | NBA games |
|---|---:|---|---:|---:|---:|
| 2018/19 | 1 | no rounds/rows returned | 26,094 | 530 | 1,230 |
| 2019/20 | 3 | no rounds/rows returned | 22,384 | 529 | 1,059 |
| 2020/21 | 5 | collected | 22,568 | 500 | 1,080 |
| 2021/22 | 7 | collected | 24,424 | 492 | 1,230 |
| 2022/23 | 9 | collected | 25,265 | 482 | 1,230 |
| 2023/24 | 13 | collected | 25,732 | 512 | 1,230 |
| 2024/25 | 19 | collected | 25,631 | 509 | 1,230 |

The API returned 5,575 player-season responses across the seven seasons; there were no request/schema errors. The 2021/22 response set contained 29 repeated player-game keys. All copies were field-for-field identical, so one copy was retained and every duplicate group was written to an audit CSV. No conflicting duplicate key was found.

The weekly-round collection covers 1,558 tasks across seasons 2020/21–2024/25, with both `avg` and `tot`, zero missing task files, no schema variants, and no empty/failed tasks. Week numbers are consecutive inside each season's discovered range. The wide dataset has 93,785 player-week-round rows; the long dataset retains 187,570 rows for the separate `avg` and `tot` views. Existing legacy averages for 2023/24 and 2024/25 match the new API table row-for-row.

## 2. NBA mapping audit

The Dunkest game-level archive was joined to NBA logs using season + game date + normalized player name + opponent code. Name variants were handled with explicit normalization/aliases. Dunkest game IDs were not assumed to be NBA game IDs; the match was not forced using score values or nearest dates.

- Dunkest game-level records: 172,098.
- Exact player/date/opponent matches to NBA player logs: 172,084 (99.9919%).
- Unmatched rows: 14, all retained in the enriched file and separately listed: 7 from 2020/21 and 7 from 2021/22.
- Crosswalk conflicts (one Dunkest ID mapping to multiple NBA player IDs): 0.

The 2018/19 and 2019/20 player-game endpoint returns real dated rows that match NBA logs, despite the weekly-round endpoint returning empty results. However, every returned row in those two seasons has `gameValidForDunkest=False`. They are preserved in the enriched archive and used as historical NBA boxscore history when identity is established, but are **not used as PDK target labels** in this strict training experiment. Their flag semantics for those legacy seasons should be verified before promoting them into target training.

A separate diagnostic compared official Dunkest PDK with the repository's current NBA-boxscore PDK proxy. Mean absolute differences were about 2.85 (2018/19), 2.91 (2019/20), 2.88 (2020/21), 2.65 (2021/22), and 0.45–0.56 in 2022/23–2024/25. This diagnostic does not identify the cause conclusively, but it shows the current proxy is not a safe way to reconstruct old labels. Training labels therefore remain sourced from the official Dunkest PDK feed.

## 3. Leakage-controlled training data

Two versions were created:

- **V1**: uses only earlier rows with `gameValidForDunkest=True` for PDK and NBA-stat lag history.
- **V2**: keeps the same strict per-game PDK target and PDK lag policy, but for NBA boxscore features it uses the most recent NBA game strictly before the target date. This includes prior NBA games even where the prior game was not marked Dunkest-valid and lets early-season rows use previous-season NBA history. The as-of join disallows exact-date matches.

Both datasets contain 93,766 labeled player-games from 2020/21–2024/25. The V2 build has 79 curated pre-game features, including lagged PDK, previous-game/rolling NBA statistics, opponent information, history count and days since the most recent NBA game. Current-game PDK and current-game boxscore statistics are excluded from the feature whitelist. V2 QA found 337 targets without an earlier NBA boxscore available, zero crosswalk identity conflicts, zero non-positive rest intervals, zero mismatches on the checked PDK lag values, and zero lag missingness mismatches.

The training artifact is an experimental player-game PDK predictor. It does not model roster selection, coach scoring, price/credits, injuries, availability or transfers.

## 4. Expanding-season walk-forward results

Test seasons are 2022/23, 2023/24 and 2024/25. For each test season, training uses only earlier seasons. Model inputs include lagged/rolling information available before the target game. PDK target labels are official Dunkest values for rows marked valid by Dunkest. These are experimental historical metrics, not a guarantee of future performance.

| Test season | RF V1 MAE | RF V2 MAE | Previous-10 mean MAE | RF V2 RMSE | Previous-10 mean RMSE |
|---|---:|---:|---:|---:|---:|
| 2022/23 | 7.6577 | 7.5783 | 7.7689 | 9.8425 | 10.1134 |
| 2023/24 | 7.6506 | 7.5971 | 7.7652 | 9.8381 | 10.1003 |
| 2024/25 | 7.6400 | 7.5886 | 7.7920 | 9.8831 | 10.1795 |
| **Mean** | **7.6494** | **7.5880** | **7.7754** | **9.8546** | **10.1311** |

V2 improves mean MAE by about 0.061 PDK versus V1 and by about 2.4% versus the mean of the previous ten valid PDK performances. The gain is consistent but modest. The three season folds share a development process and should be followed by prospective validation; do not interpret the result as an independent final benchmark.

Model files are saved separately as V1 and V2. Neither artifact is imported by `src/dunkest/pipeline/train.py` or the production lineup optimizer.

## 5. Important output files

Raw/checkpoints:
- `data/raw/dunkest_history_v2/`: weekly-round Parquet files and collection manifest.
- `data/raw/dunkest_player_games_history_v1/player_game_responses.jsonl`: resumable raw API responses.
- `data/raw/dunkest_player_games_history_v1/player_catalog_current.json`: snapshot of current public player IDs.
- `data/raw/nba_historical_logs_2018-25_v1/`: NBA player-game logs and collection manifest.

Processed:
- `data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet`
- `data/processed/dunkest_historical_stats_2020-25_v2.parquet`
- `data/processed/official_dunkest_player_games_2018-25_v1.parquet`
- `data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet`
- `data/processed/dunkest_nba_player_games_unmatched_2018-25_v1.csv`
- `data/processed/dunkest_nba_player_id_crosswalk_2018-25_v1.csv`
- `data/processed/dunkest_pdk_game_training_2020-25_v1.parquet`
- `data/processed/dunkest_pdk_game_training_2020-25_v2.parquet`
- `data/processed/dunkest_pdk_game_walk_forward_metrics_2020-25_v1.csv`
- `data/processed/dunkest_pdk_game_walk_forward_metrics_2020-25_v2.csv`
- `data/processed/dunkest_pdk_historical_random_forest_2020-25_v1.joblib`
- `data/processed/dunkest_pdk_historical_random_forest_2020-25_v2.joblib`
- `data/processed/dunkest_pdk_historical_random_forest_2020-25_v2.json`
- `data/processed/official_dunkest_player_games_2018-25_v1_duplicate_rows.csv`

Reproducible scripts:
- `scripts/collect_dunkest_historical_stats.py`
- `scripts/collect_dunkest_historical_player_games.py`
- `scripts/build_dunkest_pdk_training_dataset_v2.py`
- `scripts/validate_dunkest_historical_pdk_training.py`
- `scripts/validate_dunkest_historical_pdk_training_v2.py`
- `scripts/train_dunkest_historical_pdk_model.py`
- `scripts/train_dunkest_historical_pdk_model_v2.py`

## 6. Repository verification and safeguards

- Full test suite: **176 passed** using `PYTHONPATH="$PWD/src" ./.venv/bin/python -m pytest -q`.
- V2 artifact load/prediction smoke test: 25/25 finite predictions.
- Checked that `src/dunkest/data/dunkest/lineups_browser.py` has no diff from its existing Git state; it was not edited in this work.
- No production model or lineup-optimization code was changed for this experiment. Existing unrelated working-tree modifications were left as they were.
- V1 and V2 model artifacts, metrics and audits are separate. No existing processed dataset was overwritten except the explicitly versioned official game archive and per-season files regenerated from the same raw checkpoint after the identical-duplicate audit.

## 7. Next decision before production integration

Keep V2 as the leading experimental candidate, not yet a production replacement. Next, add a future-season or later-game prospective evaluation, inspect per-player/per-role error cohorts and calibration, and independently verify why the 2018/19 and 2019/20 `gameValidForDunkest` field is always false before considering those PDK values as official target labels.
