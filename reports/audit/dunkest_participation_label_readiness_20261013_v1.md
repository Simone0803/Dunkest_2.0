# Participation / DNP label-readiness audit

Generated UTC: 2026-10-13T10:10:26.052931+00:00

## Results by season

 season  status  nba_log_rows  unique_player_game_rows  duplicate_player_game_rows  zero_minute_rows  zero_minute_pct  missing_minute_rows  positive_minute_rows  official_pdk_target_rows_in_archive  target_archive_rows  candidate_universe_snapshot_available
2018-19 audited         26101                    26101                           0                90         0.344814                    0                 26011                                    0                    0                                  False
2019-20 audited         22393                    22393                           0                81         0.361720                    0                 22312                                    0                    0                                  False
2020-21 audited         23054                    23054                           0                84         0.364362                    0                 22970                                17662                17662                                  False
2021-22 audited         26039                    26039                           0                84         0.322593                    0                 25955                                18422                18422                                  False
2022-23 audited         25894                    25894                           0                76         0.293504                    0                 25818                                19165                19165                                  False
2023-24 audited         26401                    26401                           0               118         0.446953                    0                 26283                                18927                18927                                  False
2024-25 audited         26306                    26306                           0               100         0.380141                    0                 26206                                19590                19590                                  False
2025-26 audited         24424                    24424                           0                 1         0.004094                    0                 24423                                18412                18412                                  False

## Decision

Do not train or calibrate a participation-probability model from these logs alone. NBA player-game archives primarily contain observed appearances; absent players are not represented as explicit zero-minute outcomes. The official Dunkest PDK archive is an outcome table, not a full pre-lock roster/availability snapshot.

## Required data for a valid model

- Timestamped pre-lock full player roster/market snapshot with stable player IDs
- Fixture-linked injury/availability status captured before lock
- Post-game played/DNP/zero-minute result for every candidate, including candidates with no NBA player-game log row
- Immutable snapshot timestamp and source hash

Until those inputs are captured, keep current availability/injury rules deterministic and avoid interpreting PDK score MAE as participation accuracy. Production was not changed.

## Artifacts

- CSV: reports/audit/dunkest_participation_label_readiness_20261013_v1.csv
- JSON: reports/audit/dunkest_participation_label_readiness_20261013_v1.json
