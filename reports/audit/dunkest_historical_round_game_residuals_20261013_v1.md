# Residual unmatched historical rows — focused diagnosis v1

Generated UTC: 2026-10-13T11:26:23.879599+00:00

Only **19** rows remain after resolving the dominant team-code mismatch. They occur in season ID 5, source week 43 round 2 (16 rows) and week 53 round 2 (3 rows).

- Rows with a same-player/same-season PDK value somewhere in the official archive: **7**.
- Rows with no same-player/same-season PDK value: **12**.
- Minimum number of the 17 boxscore fields differing from the nearest same-player game: **4**; maximum: **12**.

A PDK value that appears elsewhere in the season is not a valid game link: these rows still have no exact 17-stat signature, and the matching PDK may belong to an unrelated date. The nearest-stat comparison does not repair or relabel any row. These 19 should remain excluded from exact game linkage pending source-level provenance review; do not treat them as zero or DNP.

## Artifacts
- CSV: reports/audit/dunkest_historical_round_game_residuals_20261013_v1.csv
- JSON: reports/audit/dunkest_historical_round_game_residuals_20261013_v1.json
- Report: reports/audit/dunkest_historical_round_game_residuals_20261013_v1.md
