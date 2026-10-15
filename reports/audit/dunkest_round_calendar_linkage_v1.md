# Dunkest week/round calendar linkage audit v1

## Objective
Check whether the archived historical Dunkest weekly/round tables can independently validate the game-level `gameValidForDunkest` flag.

## Game-level archive by season

| Season | Rows | Date range | Flag true | Flag false | NBA matched |
|---|---:|---|---:|---:|---:|
| 2018-19 (ID 1) | 26,094 | 2018-10-16 – 2019-04-10 | 0 | 26,094 | 26,094 |
| 2023-24 (ID 13) | 25,732 | 2023-10-24 – 2024-04-14 | 18,927 | 6,805 | 25,732 |
| 2024-25 (ID 19) | 25,631 | 2024-10-22 – 2025-04-13 | 19,590 | 6,041 | 25,631 |
| 2019-20 (ID 3) | 22,384 | 2019-10-22 – 2020-08-14 | 0 | 22,384 | 22,384 |
| 2020-21 (ID 5) | 22,568 | 2020-12-22 – 2021-05-16 | 17,662 | 4,906 | 22,561 |
| 2021-22 (ID 7) | 24,424 | 2021-10-19 – 2022-04-10 | 18,422 | 6,002 | 24,417 |
| 2022-23 (ID 9) | 25,265 | 2022-10-18 – 2023-04-09 | 19,165 | 6,100 | 25,265 |

## Weekly archive coverage

| Season ID | Files | Rows | Weeks | Rounds | Date/game-ID columns |
|---:|---:|---:|---:|---|---|
| 13 | 308 | 37,854 | 1–62 (62 distinct) | 1, 2, 3 | none |
| 16 | 58 | 870 | 1–25 (23 distinct) | 1, 2, 3 | none |
| 19 | 316 | 39,180 | 1–64 (64 distinct) | 1, 2, 3, 4 | none |
| 22 | 70 | 1,038 | 1–27 (25 distinct) | 1, 2 | none |
| 25 | 5 | 64 | 1–3 (3 distinct) | 1, 2 | none |

## Findings

- The enriched game-level archive has dated game rows and the flag, but these alone do not identify the fantasy-round calendar rule.
- Archived week/round parquet files are player aggregates keyed by season/week/round and avg/tot; the inspected schemas contain no game date, timestamp, NBA game ID, or per-game key.
- Weekly archive coverage is uneven across seasons; only seasons with files can be compared, and even those files do not directly map a fantasy round to a date interval.
- Therefore a direct independent validation of gameValidForDunkest from these archives is not possible without a dated Dunkest round calendar, timestamped snapshot, or another authoritative source linking rounds to games.

## Decision

Do not infer or relabel the flag from weekly archives. Keep raw gameValidForDunkest and official PDK unchanged; retain the strict official-target policy and existing walk-forward splits.

## Guardrails

- No changes to raw game data, PDK values, training targets, production model, validation splits, or walk-forward settings.
- No commit, revert, or overwrite of existing artifacts.
- Full machine-readable inventory: `reports/audit/dunkest_round_calendar_linkage_v1.json`.
