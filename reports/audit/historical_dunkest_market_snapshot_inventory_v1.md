# Historical Dunkest market/snapshot inventory — V1

Generated (UTC): 2026-10-12T11:35:18.727024+00:00

## Conclusion

The repository contains extensive historical Dunkest player-week/round statistics, including both `cr` and `pdk`, but those tables do not carry a capture timestamp or a verified pre-game as-of marker. They must not be treated as exact pre-game market snapshots without additional source validation.

The `data/predictions/*/pre_match_snapshot/` directories are the only clearly point-in-time bundles found. They contain credits, coaches, injuries, availability and fixture mappings, but cover the current 2026/27 opener capture period rather than earlier seasons. Therefore the current roster adjustment cannot yet be validated historically against the exact market/availability state available before each past game.

## Historical weekly-round archives

| Folder | Files | Rows summed across files | Season IDs |
|---|---:|---:|---|
| `dunkest_history` | 757 | 79,006 | 13: 308 files, weeks 1–62 (154 week/rounds); 16: 58 files, weeks 1–25 (29 week/rounds); 19: 316 files, weeks 1–64 (158 week/rounds); 22: 70 files, weeks 1–27 (35 week/rounds); 25: 5 files, weeks 1–3 (5 week/rounds) |
| `dunkest_history_v2` | 1558 | 187,570 | 5: 280 files, weeks 1–59 (140 week/rounds); 7: 330 files, weeks 1–64 (165 week/rounds); 9: 324 files, weeks 1–64 (162 week/rounds); 13: 308 files, weeks 1–62 (154 week/rounds); 19: 316 files, weeks 1–64 (158 week/rounds) |

The `avg` and `tot` files are alternative representations of the same weekly-round result table, not independent pre-game snapshots.

## Processed historical tables inspected

| Dataset | Rows | Key fields relevant to this audit |
|---|---:|---|
| `daily_historical_pdk_2025-26.parquet` | 25,659 | cr, pdk, min, starter, api_date |
| `dunkest_historical_player_week_round_2020-25_v2.parquet` | 93,785 | cr, plus, starter, source_week, source_round |
| `dunkest_historical_stats_2020-25_v2.parquet` | 187,570 | cr, pdk, plus, min, starter, source_week, source_round |
| `plusvalenza_history_22_through_gw91_v2.parquet` | 519 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_24_through_gw91_v2.parquet` | 377 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_25.parquet` | 271 | cr, pdk, plus, min, starter, gameweek |
| `plusvalenza_history_25_through_gw91_v2.parquet` | 1,858 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_multiseason_26_pre_gw0_5y_nba_v3.parquet` | 41,329 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_multiseason_26_pre_gw0_5y_v2.parquet` | 2,754 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_nba_13_through_gw91_v3.parquet` | 18,927 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_nba_16_through_gw91_v3.parquet` | 435 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_nba_19_through_gw91_v3.parquet` | 19,590 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_nba_22_through_gw91_v3.parquet` | 519 | cr, pdk, plus, min, starter, gameweek, season_id |
| `plusvalenza_history_nba_25_through_gw91_v3.parquet` | 1,858 | cr, pdk, plus, min, starter, gameweek, season_id |

## Archived point-in-time snapshot bundles

Found **31** run-level `pre_match_snapshot` bundles.

| Run ID | Files captured |
|---|---|
| `20261008T093000Z_3051df18` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (62 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (573 rows) |
| `20261008T094331Z_12d79429` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (84 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (573 rows) |
| `20261008T100031Z_a02fed37` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (84 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (573 rows) |
| `20261009T135323Z_fb0fee15` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (97 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261009T141219Z_18e83d63` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (97 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261009T141921Z_39483857` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (97 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261009T142424Z_2c78a7be` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (97 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261009T150558Z_4e8ff850` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), injuries_26_gw1.parquet (97 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261010T083359Z_22ec70d9` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_first_appearance_v1.parquet (16 rows), injuries_26_gw1.parquet (39 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261010T085257Z_5076b845` | coach_market_26_gw1.parquet (6 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_lineups_turn1.parquet (3 rows), injuries_26_gw1.parquet (39 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261010T131128Z_df206ae1` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_lineups_turn1.parquet (3 rows), injuries_26_gw1.parquet (23 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (553 rows) |
| `20261010T132258Z_86251ef3` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_lineups_turn1.parquet (3 rows), injuries_26_gw1.parquet (23 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (553 rows) |
| `20261010T135249Z_830f6057` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_lineups_turn1.parquet (3 rows), injuries_26_gw1.parquet (28 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (543 rows) |
| `20261010T144213Z_100ee7de` | coach_market_26_gw1.parquet (6 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_lineups_turn1.parquet (3 rows), injuries_26_gw1.parquet (39 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (548 rows) |
| `20261010T144856Z_28b368a0` | coach_market_26_gw1.parquet (6 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_g1_lineups_turn1.parquet (3 rows), injuries_26_gw1.parquet (39 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (548 rows) |
| `20261012T085417Z_327ebd5e` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (2 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (569 rows) |
| `20261012T090223Z_464324bb` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T093023Z_01411bbd` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T093847Z_2b4a2ab6` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T093945Z_6f9fc7a3` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T094038Z_43bedafe` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T094126Z_2bb5f9bb` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T094835Z_9a175ece` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T095005Z_538872ad` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T095227Z_f4f126c9` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T095616Z_e0474c53` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (1 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (570 rows) |
| `20261012T102807Z_869c3c41` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (3 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (568 rows) |
| `20261012T103952Z_6c140c29` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (5 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (566 rows) |
| `20261012T105557Z_d94a9ea8` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (86 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (566 rows) |
| `20261012T105854Z_4bc44e97` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (86 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (566 rows) |
| `20261012T110150Z_652b80ff` | coach_market_26_gw1.parquet (30 rows), current_lineups_market.csv (? rows), dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet (16 rows), injuries_26_gw1.parquet (86 rows), lineups_availability.csv (? rows), player_credits_26_gw1.parquet (566 rows) |

## Consequences for model validation

1. Keep the current production roster adjustment unchanged; the previous PDK aggregate proxy failed to improve walk-forward probability metrics.
2. Use official historical PDK and NBA logs for leakage-safe player-form/score validation; use prior-round `cr` only as a lagged price proxy if needed.
3. Do not claim historical injury/coach/availability validation from current snapshots: the exact historical states are not archived here.
4. Begin prospective immutable snapshot capture every run, retaining retrieval timestamps, raw payload hashes, fixture IDs and the precise pre-game cutoff. This will create a defensible 2026/27+ evaluation set.

## Reproducibility

```bash
PYTHONPATH="$PWD/src" ./.venv/bin/python scripts/audit_historical_dunkest_market_snapshots_v1.py
```
