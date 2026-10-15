# Dunkest official schedule vs archive — 2024/25 (v2, status-aware)

- Official schedule ID: `19`
- Matchday IDs scanned: `500–850`
- Matchdays with matches: **64**
- Official schedule records: **1040** (1037 played, 2 postponed)
- Official date range: **2024-10-22 – 2025-04-11**
- Played team-side comparisons: **2074**
- Played team sides matched locally: **2074/2074 (100.00%)**
- Exact `gameValidForDunkest` agreement among matched played sides: **2074/2074 (100.00%)**

## Postponed entries

- 2025-01-09 LAL–CHA (matchday 695, status `postponed`); correctly excluded from played-game matching.
- 2025-01-22 NOP–MIL (matchday 700, status `postponed`); correctly excluded from played-game matching.

## Played-game anomalies

- No unmatched played team sides.
- No validity-flag mismatches among matched played team sides.

## Interpretation

The two apparent archive gaps in v1 were both explicitly marked `postponed` by the official API, not missing played box scores. Once postponed entries are excluded from the played-game denominator, the archive matches every played official team side and all validity flags agree. Read-only audit; no raw dataset, PDK target, model, temporal split, or backtest was modified.
