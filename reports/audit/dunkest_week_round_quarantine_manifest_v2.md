# Dunkest weekly-round quarantine/review manifest (v2)

Generated UTC: 2026-10-12T15:02:41.754958+00:00

## Decision policy

Only the confirmed 15-player PHI–MIN cluster is quarantined from future clean derivatives. Four isolated exact full-boxscore matches are documented below but remain manual-review candidates. A single-player signature is not sufficient to automatically discard a complete weekly-round file. Raw data remains unchanged.

## Confirmed quarantine

- `data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet`
- `data/raw/dunkest_history_v2/season_5_week_43_round_2_tot.parquet`
- Evidence: 15 players map exactly to PHI–MIN on 2021-11-27, NBA game `0022100292`, and official season-7 player history; 15/15 PDK values agree at table precision. Live endpoint requests reproduce the same cluster under `season_id=5`.

## Isolated exact-signature candidates (review only)

| Source scope | Player | Actual NBA game | Table PDK | Official-history PDK | PDK agrees at 1dp? |
|---|---|---|---:|---:|---|
| `season_13_week_20_round_1` | Jaden Springer | BOS vs. SAC, 2025-01-10 (`0022400528`) | 0.00 | 0.0 | True |
| `season_5_week_40_round_3` | Juan Toscano-Anderson | GSW vs. WAS, 2022-03-14 (`0022101025`) | -3.00 | 3.0 | False |
| `season_5_week_53_round_2` | Nickeil Alexander-Walker | NOP @ DEN, 2022-02-04 (`0022100794`) | 13.00 | 13.0 | True |
| `season_9_week_40_round_2` | Sandro Mamukelashvili | SAS @ BKN, 2024-02-10 (`0022300750`) | 2.10 | 2.0 | False |

### Required interpretation

- Jaden Springer (season 13, week 20, round 1): exact 15-field boxscore signature; PDK agrees.
- Nickeil Alexander-Walker (season 5, week 53, round 2): exact signature; PDK agrees.
- Juan Toscano-Anderson (season 5, week 40, round 3): exact signature; table PDK −3.0 vs official history +3.0; unresolved.
- Sandro Mamukelashvili (season 9, week 40, round 2): exact signature; table PDK 2.1 vs official history 2.0; unresolved.

A separate Sandro candidate at season 9/week 20/round 2 remains in the broad candidate review because one boxscore field (3PA) differs; it is not counted among the four exact 15-field matches.

## Public endpoint query test

Read-only live requests returned 118 rows for season 5/week 43/round 2 in both `avg` and `tot`. Requests using minimal parameters and the collector-style explicit team/position/sort filters produced identical payload hashes for both stats types. The same scope queried under season ID 7 returned 143 rows with a different hash. This rules out the missing optional team/position/sort filters as the cause of the observed response, but does not identify the server-side cause. The explicit `season_id` is present in requests. See `dunkest_stats_endpoint_scope_v1.md`.

## Safety

The two confirmed source files are the only files marked for quarantine. Four singleton candidates and other scan candidates remain review-only. No raw Parquet, target, validity flag, model, config, split, or backtest was modified.

JSON: `reports/audit/dunkest_week_round_quarantine_manifest_v2.json`
CSV: `reports/audit/dunkest_week_round_quarantine_manifest_v2.csv`
