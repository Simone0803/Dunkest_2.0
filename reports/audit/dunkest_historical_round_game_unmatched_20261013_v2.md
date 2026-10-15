# Historical Dunkest unmatched weekly rows — diagnostic v2

Generated UTC: 2026-10-13T11:20:48.567497+00:00

## Purpose

The v1 full-signature audit found **7,892 unmatched `gp=1` rows**. This diagnostic classifies them using official-archive candidate counts and exact boxscore-stat signatures independent of PDK. It does not repair or relabel records.

## Classification

- `player_team_exist_but_pdk_or_boxscore_stats_differ`: **6,726 (85.2%)**
- `player_team_and_pdk_exist_but_boxscore_signature_differs`: **1,032 (13.1%)**
- `player_exists_in_season_but_team_differs_or_trade_alias`: **128 (1.6%)**
- `boxscore_stats_match_but_pdk_or_other_signature_field_differs`: **6 (0.1%)**

## Key checks

- Rows with at least one same-season player/team official record: **7,764**.
- Rows with exact 17-stat signature match when PDK is ignored: **6**.
- Rows with same-season player/team/PDK candidate but differing boxscore signature: **1,035**.
- Unmatched rows span **555** season-week-round groups.

## Interpretation limits

- Candidate counts are evidence for diagnosing archive joins, not proof of a valid date/game association.
- A statistics match with a different PDK indicates a discrepancy to investigate; it does not establish which PDK is authoritative for training.
- A player/team mismatch can reflect a trade, identity mapping, source convention, or archive coverage. No automatic alias correction is applied.
- Missing archive records are not negative participation labels, zero scores, or evidence of ineligibility.
- Production model, source datasets, training labels, and frozen prospective holdout remain unchanged.

## Artifacts

- Row-level classifications: `reports/audit/dunkest_historical_round_game_unmatched_20261013_v2_rows.csv`
- Season summary: `reports/audit/dunkest_historical_round_game_unmatched_20261013_v2_seasons.csv`
- Round summary: `reports/audit/dunkest_historical_round_game_unmatched_20261013_v2_rounds.csv`
- JSON: `reports/audit/dunkest_historical_round_game_unmatched_20261013_v2.json`
