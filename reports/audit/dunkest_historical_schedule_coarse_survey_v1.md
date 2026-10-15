# Historical Dunkest schedule-ID coarse survey (v1)

- Endpoint: `GET /api/v1/schedules/{schedule_id}/matchdays/{matchday_id}`.
- Schedule IDs surveyed: **1–49**.
- Sampled global matchday IDs: **80** (step 20 from 1 through 1,581).
- Requests attempted: **3,920**.
- NBA-like matchday records found in the sample: **15**.
- Read-only; no account credentials or production data were changed.

## Matches found

| Schedule ID | Sample matchday ID | Matchday number | Match records | Date range (UTC) |
|---:|---:|---:|---:|---|
| 1 | 1 | 1 | 16 | 2022-10-18T23:30:00.000000Z – 2022-10-21T02:00:00.000000Z |
| 1 | 21 | 20 | 16 | 2022-12-07T00:30:00.000000Z – 2022-12-09T03:00:00.000000Z |
| 1 | 41 | 40 | 16 | 2023-01-28T20:00:00.000000Z – 2023-01-31T01:00:00.000000Z |
| 1 | 61 | 60 | 15 | 2023-03-31T23:00:00.000000Z – 2023-04-02T00:30:00.000000Z |
| 3 | 101 | 5 | 7 | 2023-04-24T23:30:00.000000Z – 2023-04-27T02:00:00.000000Z |
| 8 | 281 | 18 | 16 | 2023-12-17T20:00:00.000000Z – 2023-12-19T03:30:00.000000Z |
| 8 | 301 | 38 | 17 | 2024-02-09T00:00:00.000000Z – 2024-02-10T20:30:00.000000Z |
| 8 | 321 | 58 | 17 | 2024-04-04T23:30:00.000000Z – 2024-04-06T23:00:00.000000Z |
| 19 | 681 | 16 | 17 | 2024-11-29T17:00:00.000000Z – 2024-12-02T03:00:00.000000Z |
| 19 | 701 | 36 | 17 | 2025-01-25T00:00:00.000000Z – 2025-01-26T23:00:00.000000Z |
| 19 | 721 | 56 | 15 | 2025-03-21T23:00:00.000000Z – 2025-03-23T02:30:00.000000Z |
| 36 | 1221 | 11 | 16 | 2025-11-15T22:00:00.000000Z – 2025-11-18T00:30:00.000000Z |
| 36 | 1241 | 31 | 16 | 2026-01-10T00:00:00.000000Z – 2026-01-11T02:30:00.000000Z |
| 36 | 1261 | 51 | 17 | 2026-03-09T23:00:00.000000Z – 2026-03-12T00:00:00.000000Z |
| 36 | 1281 | 71 | 8 | 2026-04-28T00:00:00.000000Z – 2026-04-30T02:00:00.000000Z |

## Interpretation

- NBA regular-season schedules sampled: **1 (2022/23), 8 (2023/24), 19 (2024/25), 36 (2025/26)**.
- Schedule **3** yielded NBA playoff games in April 2023, not a regular-season schedule.
- No NBA regular-season schedule dated before 2022/23 was found in this coarse sample.
- This was a bounded coarse survey, not an exhaustive query of every pair of IDs. A schedule whose matchday IDs did not intersect the sample could be missed, so the historical seasons 2018/19–2021/22 remain **unresolved**, not proven absent.
- Stats API season IDs and schedule IDs are distinct identifiers; never infer schedule IDs from stats season IDs.
