# Historical Dunkest round-to-game mapping audit — v1

Generated UTC: 2026-10-13T11:14:29.305192+00:00

## Method

For rows with `gp=1`, this audit matches the historical `tot` table to the official player-game archive on season, canonical player identity, NBA team, PDK rounded to two decimals, and 17 boxscore fields. PDK-only joins are not used as final evidence. Source data and labels are read-only.

## Coverage

- Source weekly-round rows inspected: **93,785**.
- Rows with `gp=1` audited: **93,779**.
- Unique full-signature matches: **85,477 (91.1%)**.
- Ambiguous signatures: **410**.
- No full-signature match: **7,892**.
- Week-rounds: **779**; one mapped date in **773**, multiple mapped dates in **6**.
- Median unique-signature coverage per round: **89.5%**; median mapped team count: **12**.

## Example: season 9, week 22, round 3 (2022-12-13)

- Source rows: **23**; unique full-signature matches: **19**; unmatched rows: **4**.
- Teams in source table: `GSW;LAL;MIN;UTA`.
- Teams represented by unique signature matches: `GSW;UTA`.
- Teams with observed `gameValidForDunkest=True` among linked rows: `GSW;UTA`.

This explains why a PDK-only target-date join can make the optimizer see a team (for example, a team whose source row does not match that date’s boxscore) while omitting other teams: the outcome table is not a full pre-lock market snapshot. It does not establish why any individual unmatched row is absent or whether it should be relabelled.

## Findings

- Full boxscore signatures are substantially more specific than PDK-only date joins, which can map the same score to multiple dates and inject unrelated teams into a round matchup map.
- A unique game link is evidence that a weekly row resembles a specific NBA boxscore, not proof that the archive contains the full eligible market or that every missing row is a zero.
- A source round may have a clean dominant date but only a subset of teams/player rows. These tables are outcome archives, not complete pre-lock candidate snapshots.
- Do not automatically repair, remove, relabel, or train on unmatched rows based on this audit. Do not change production model, official labels, or the frozen 2026/27 GW1 holdout.

## Decision and guardrails

- Keep the historical weekly tables as outcome archives; do not use them alone to claim complete pre-lock market coverage.
- Keep the production team cap, prediction model, official PDK values, and temporal splits unchanged.
- Do not inspect or tune against the frozen prospective 2026/27 GW1 holdout before its cutoff.
- No source data, production code/config, or existing versioned artifact was modified by this audit.

## Artifacts

- Row-level audit: `reports/audit/dunkest_historical_round_game_mapping_20261013_v1_rows.csv`
- Round summary: `reports/audit/dunkest_historical_round_game_mapping_20261013_v1_rounds.csv`
- JSON: `reports/audit/dunkest_historical_round_game_mapping_20261013_v1.json`
