# Dunkest project follow-up — historical weekly-round integrity (v3)

Date: 2026-10-12
Status: read-only historical-source verification; one confirmed cross-season contamination cluster found. No source data or production behavior changed.

## Executive summary

The weekly-round archive in `data/raw/dunkest_history_v2` is internally well-formed, but **it cannot be treated as fully season-scoped**. A table labelled stats `season_id=5` (expected 2020/21 in the project's mapping) contains 15 player rows whose complete boxscore signatures match the same NBA game from 2021/22, 2021-11-27, Philadelphia vs Minnesota. A live re-query of the public stats endpoint reproduced the same 15-player cluster in both `avg` and `tot` responses.

The finding is not inferred from one PDK value: all 15 rows match the NBA boxscore signature, all 15 have official player-game history rows under season ID 7 on that date, all 15 are flagged `gameValidForDunkest=True`, and all 15 PDK values agree after rounding the one-decimal table values using half-up rounding. This establishes a genuine cross-season scope problem for that source response.

## 1. Verified contamination cluster

- Weekly table scope: `season_id=5`, week 43, round 2.
- Files: `season_5_week_43_round_2_avg.parquet` and `season_5_week_43_round_2_tot.parquet`.
- Each response contains 118 rows; the same 15 players correspond to NBA game ID `0022100292`, dated 2021-11-27 (PHI vs MIN), which belongs to 2021/22.
- All 15 have a matching row in `official_dunkest_player_games_2018-25_v1.parquet` under season ID 7 and are valid there.
- The PDK values match at the weekly table's one-decimal precision using decimal `ROUND_HALF_UP` (the totals table retains the more precise values).
- The read-only endpoint re-query returned the same 118-row response and same 15 players for both `stats_type=avg` and `stats_type=tot`.

Detailed evidence:
- `reports/audit/dunkest_week_round_season5_contamination_v2.md`
- `reports/audit/dunkest_week_round_season5_contamination_v2.json`
- `reports/audit/dunkest_week_round_season5_contamination_v2.csv`

## 2. Cross-archive checks

The comparison of all weekly `avg` tables with official player-game history, grouped by player and comparing score multisets at one-decimal precision:

| Stats season ID | Expected season | Weekly table rows | Official `gameValidForDunkest=True` rows | Player score multisets |
|---:|---|---:|---:|---|
| 5 | 2020/21 | 17,681 | 17,662 | Mismatch: 25 table-only score entries and 6 history-only entries (net +19 table rows) |
| 7 | 2021/22 | 18,422 | 18,422 | Exact match for all 492 player groups |
| 9 | 2022/23 | 19,165 | 19,165 | Exact match for all 482 player groups |
| 13 | 2023/24 | 18,927 | 18,927 | Exact match for all 512 player groups |
| 19 | 2024/25 | 19,590 | 19,590 | Exact match for all 509 player groups |

The exact per-player score multiset match for seasons 7, 9, 13 and 19 is a strong internal consistency check, but not a date-level linkage proof because the weekly tables do not contain a usable game date. Matching score distributions alone can also hide coincidental repeated scores. Season 5 is clearly discrepant and the confirmed 15-player cluster demonstrates why row counts alone are insufficient.

A broader boxscore-signature scan produced 45 isolated cross-season candidate rows in each of the `avg` and `tot` archives. The only multi-player cluster meeting the conservative threshold was the 15-player PHI–MIN game above (split into home/away matchup strings in the report). Isolated matches are not classified as errors without corroboration.

Detailed broad scan:
- `reports/audit/dunkest_week_round_cross_season_integrity_v2.md`
- `reports/audit/dunkest_week_round_cross_season_integrity_v2.json`
- `reports/audit/dunkest_week_round_cross_season_integrity_v2.csv`

## 3. Interpretation and safeguard

The weekly-round API's returned rows must not be trusted as season-correct solely because `season_id`, week and round were supplied. The confirmed response suggests at least one source-scope/cache/data-association defect or equivalent historical inconsistency; its exact backend cause is not established.

Actions deliberately **not** taken:
- no rows deleted, filtered or relabelled in the raw weekly-round archive;
- no changes to official PDK labels or `gameValidForDunkest` flags;
- no changes to training targets, features, temporal splits, model artifacts, production configuration or backtests;
- no attempt to infer missing official targets from boxscore proxies.

## 4. Next verification steps

1. Quarantine the confirmed table scope in a *separate audit manifest*, not in the raw archive.
2. Scan every remaining weekly-round response against official player-game history and NBA boxscores, looking for multi-player cross-season clusters and comparing `avg`/`tot` row signatures.
3. Determine whether the public endpoint returns the contamination consistently across repeated read-only calls and whether a different query shape changes the response. Do not bypass authentication.
4. Only after the affected scopes are enumerated, build a new clean derivative with explicit provenance and exclusions; leave the original archive untouched.

## 5. Tests

The full project suite passed after adding the audit tooling: **213 passed**, 6,800 warnings (primarily PuLP deprecations and one market freshness warning). The audit scripts compile successfully. No production code paths were changed by these audits.
