# Official Dunkest schedule vs local archive — v2 (status-aware)

- Official schedule records: **2055**
- Status counts: `{"played": 2054, "postponed": 1}`
- Played NBA games: **2054**
- Postponed records excluded from played-game matching: **1**
- Played team sides matched: **4108/4108 (100.00%)**
- Exact validity flags among played sides: **4107/4108 (99.98%)**

## Schedule-level summary

| Schedule ID | Official records | Played | Postponed | Team sides matched / compared | Exact validity flags / matched sides |
|---:|---:|---:|---:|---:|---:|
| 1 | 1041 | 1040 | 1 | 2080/2080 | 2080/2080 |
| 8 | 1014 | 1014 | 0 | 2028/2028 | 2027/2028 |

## Postponed entries

- 2023-02-01 DET–WAS (schedule 1, matchday 42, status `postponed`).

## Remaining played-game mismatch

- 2023-12-12 BOS–CLE: API home/away validity `True/False`; archive `[False]/[False]`.

## Interpretation

The apparent Detroit–Washington archive gap is explained by the official `postponed` status, not by a missing played box score. All 4,108 team sides from the 2,054 played games match the archive. One validity discrepancy remains for Boston–Cleveland on 2023-12-12; it is preserved as unresolved. No data or model artifacts were changed.
