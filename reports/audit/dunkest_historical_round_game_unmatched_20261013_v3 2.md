# Historical Dunkest unmatched weekly rows — team identity diagnosis v3

Generated UTC: 2026-10-13T11:23:49.227513+00:00

## Result

The v1 audit had **7,892** unmatched rows under the strict season + player + team + PDK + 17-stat signature. When the source team field is excluded but season, canonical player, PDK and all 17 statistics remain exact, **7,873/7,892 (99.8%)** find an official game candidate.

- Exact PDK + 17-stat match, but source team differs: **7,873 (99.8% of unmatched rows)**.
- Exact PDK + 17-stat match, source team agrees: **0**.
- Boxscore statistics match but PDK differs (ignoring team): **0**.
- No exact 17-stat signature even when team and PDK are ignored: **19**.

## Interpretation

The dominant issue is the source team identity attached to the historical weekly row, not the PDK value or the 17 boxscore fields: for almost all unmatched rows, the same player-game outcome and PDK are present in the official archive under a different NBA team code. This is consistent with a current/round-level roster association being attached to historical game stats, but this audit alone does not establish the exact upstream mechanism or whether team_code is intended to mean historical game team versus Dunkest team assignment.

Do not simply overwrite team_code with the matched NBA team. Preserve source semantics until they are documented. Any future backtest must use the official game team/date for matchup features while separately retaining the Dunkest fantasy-team identity if that is what the weekly source field encodes.

## Guardrails

- Diagnostic only; no data correction or label change was applied.
- Do not treat unmatched rows as zero, DNP, or ineligible outcomes.
- Production model/configuration and the frozen 2026/27 GW1 holdout are unchanged.
- The holdout remains frozen until **2026-10-23 12:00 UTC**.

## Artifacts
- Row-level exact candidate/team comparisons: reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rows.csv
- Season summary: reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_seasons.csv
- Week-round summary: reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rounds.csv
- JSON: reports/audit/dunkest_historical_round_game_unmatched_20261013_v3.json
