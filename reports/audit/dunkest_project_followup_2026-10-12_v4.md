# Dunkest project follow-up — historical source scope verification (v4)

Date: 2026-10-12
Status: read-only cross-source audit. One confirmed multi-player cross-season cluster plus four isolated exact-boxscore candidates found. No source data or production behavior changed.

## Summary

The weekly-round API archive is structurally valid, but at least some returned rows are not scoped to the season ID under which they were collected. The clearest case is a 15-player Philadelphia–Minnesota game from 2021/22 appearing in the table labelled season ID 5 (expected 2020/21). A second, stricter scan found four isolated rows whose complete boxscore signatures uniquely match NBA games from a different season; two also match official-history PDK at one-decimal precision, while two have unresolved PDK discrepancies.

Do not use the weekly-round archive as a verified season-specific label source until these scopes are reconciled. Keep all raw files unchanged and build any future cleaned derivative separately.

## 1. Exact boxscore-signature scan

The audit started from 45 cross-season candidates and checked the paired `tot` tables against NBA logs using player, team, and 15 boxscore fields. It found 19 exact row matches:

| Source table scope | Actual NBA game | Exact rows | PDK agrees with official history at 1dp | Status |
|---|---|---:|---:|---|
| `season_5_week_43_round_2` | PHI–MIN, 2021-11-27, game `0022100292` | 15 | 15/15 | Confirmed multi-player cross-season cluster |
| `season_13_week_20_round_1` | BOS–SAC, 2025-01-10, game `0022400528` | 1 (Jaden Springer) | 1/1 | Isolated exact-signature candidate |
| `season_5_week_40_round_3` | GSW–WAS, 2022-03-14, game `0022101025` | 1 (Juan Toscano-Anderson) | 0/1 | Isolated candidate; PDK discrepancy unresolved |
| `season_5_week_53_round_2` | NOP–DEN, 2022-02-04, game `0022100794` | 1 (Nickeil Alexander-Walker) | 1/1 | Isolated exact-signature candidate |
| `season_9_week_40_round_2` | SAS–BKN, 2024-02-10, game `0022300750` | 1 (Sandro Mamukelashvili) | 0/1 | Isolated candidate; PDK discrepancy unresolved |

The PHI–MIN cluster is the strongest finding: the same 15 players, from one NBA game, appear in both `avg` and `tot` outputs for season ID 5. Each has a matching season-ID-7 official player-game record marked valid, and all PDK values agree at table precision. The live endpoint re-query reproduced the same 118-row response and 15-player cluster for both `avg` and `tot`.

Detailed files:
- `reports/audit/dunkest_week_round_boxscore_signature_corroboration_v1.md`
- `reports/audit/dunkest_week_round_boxscore_signature_corroboration_v1.json`
- `reports/audit/dunkest_week_round_boxscore_signature_corroboration_v1.csv`
- `reports/audit/dunkest_week_round_season5_contamination_v2.md`

## 2. Official-history corroboration of isolated candidates

Across 45 unique cross-season candidates from the broad signature scan:
- 37 have an official player-history row for the candidate player/date/season.
- 18 agree with official-history PDK after half-up rounding to one decimal.
- 15 of those 18 belong to the confirmed PHI–MIN cluster.
- Three isolated candidates also have PDK agreement: Jaden Springer (season 13 table, 2024/25), Nickeil Alexander-Walker (season 5 table, 2021/22), and Sandro Mamukelashvili (season 9 table, 2023/24). These remain isolated candidates, not multi-player clusters.
- PDK mismatches and missing history matches are unresolved; they are not automatically labelled bad data.

Details: `reports/audit/dunkest_week_round_history_corroboration_v1.md` and its CSV/JSON companions.

## 3. Aggregate score-distribution check — limited scope

Per-player score multisets in the weekly `avg` tables match official `gameValidForDunkest=True` history at one-decimal precision for season IDs 7, 9, 13 and 19. Season ID 5 has 17,681 weekly rows versus 17,662 official valid rows, with 25 table-only and 6 history-only score entries. The exact cross-season rows demonstrate why aggregate counts or score distributions alone cannot certify correct season assignment.

## 4. Quarantine policy

- Quarantine the entire source scope `season_5_week_43_round_2` (`avg` and `tot`) from any future clean derivative until it is re-fetched and reconciled.
- Keep the four isolated exact-signature scopes on a manual-review list; do not automatically remove whole files on singleton evidence.
- Keep the remaining isolated signature candidates as review-only, not confirmed errors.
- Preserve all raw files and their original values.

Manifest: `reports/audit/dunkest_week_round_quarantine_manifest_v1.md`.

## 5. Tests and safeguards

The full project suite passed: **213 passed**, 6,800 warnings (mainly PuLP deprecations and one market-freshness warning). Audit scripts compile successfully. No source Parquet, manifest, PDK target, validity flag, training feature, model, production configuration, temporal split or backtest was changed.

## Next step

Investigate the public stats endpoint's historical query behavior and the four isolated scopes using only read-only requests. After the affected rows are enumerated, create a new cleaned derivative with explicit provenance and quarantine rules. Do not overwrite the raw archive or integrate it into training yet.
