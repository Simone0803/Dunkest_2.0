# Downstream impact of confirmed weekly-round contamination — V1

Generated UTC: 2026-10-12T20:55:41.545609+00:00

## Confirmed source issue

- Cluster: **15 players** in MIN @ PHI on 2021-11-27 (NBA game 22100292).
- Scope: season ID 5, week 43, round 2.
- Quarantined files: data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet, data/raw/dunkest_history_v2/season_5_week_43_round_2_tot.parquet

## Downstream checks

| Dataset / path | Result |
|---|---|
| Processed weekly-round table | 118 rows in the affected round; 15 confirmed bad player rows identified |
| Historical collector guard | Excludes exactly 15 confirmed rows from season-specific ID seeding |
| Official 2020/21 player history | 22,568 rows; 17,662 valid rows; dates 2020-12-22–2021-05-16 |
| PDK training V3, season 2020/21 | 17,662 rows; latest date 2021-05-16; rows after 2021-06-30: 0 |
| Current 2026/27 capital-gain cache | Season IDs 13, 16, 19, 22, 25; season ID 5 included: no |

## Interpretation

The confirmed contamination is confined to two weekly-round source files and their derived weekly-round table. The official 2020/21 per-player history and PDK training targets contain no post-season dates, the season-5 training row count matches the official valid-row count, and the current 2026/27 capital-gain cache does not include season_id=5. The historical collector now excludes only the 15 confirmed bad rows from season-specific ID seeding. This does not certify the remaining weekly-round archive as clean.

The PDK training target is sourced from official per-player game history and verified NBA matches, not the weekly-round Parquet. The weekly-round derivative remains uncertified and must not be used as a training target or trusted same-round pre-game feature.

## Reproducibility

    PYTHONPATH=src ./.venv/bin/python scripts/audit_dunkest_week_round_contamination_impact_v1.py
