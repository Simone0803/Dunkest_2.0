# Dunkest official schedule vs archive — 2024/25 (v3, status-aware)

- Schedule ID: `19`
- Matchday IDs scanned: `500–850`
- Matchdays with matches: **64**
- Official schedule records: **1040**
- API statuses: `{"played": 1037, "playing": 1, "postponed": 2}`
- Archive-backed games (status `played` plus one `playing` record verified in the archive): **1038**
- Postponed records excluded from played-game matching: **2**
- Archive-backed team-side comparisons: **2076**
- Archive-backed team sides matched: **2076/2076 (100.00%)**
- Exact validity-flag agreement among matched sides: **2076/2076 (100.00%)**

## Postponed entries

- 2025-01-09 LAL–CHA (matchday 695); API status `postponed`.
- 2025-01-22 NOP–MIL (matchday 700); API status `postponed`.

## API status discrepancy

- 2024-12-29 MIN–SAS (matchday 691): API status `playing`, but both team sides and validity flags are present in the local archive.

## Remaining anomalies

- No unmatched archive-backed team sides.
- No validity-flag mismatches among matched archive-backed team sides.

## Interpretation

The two unmatched schedule records are postponed games, not missing played box scores. One old API status remains `playing` despite the game and both validity flags being present in the archive; it is retained as a status-quality issue, not silently rewritten. Read-only audit; no source parquet, PDK target, model, temporal split, or backtest was modified.
