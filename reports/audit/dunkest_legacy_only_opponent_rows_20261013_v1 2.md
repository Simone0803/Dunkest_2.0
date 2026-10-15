# Audit of legacy-only opponent coverage — v1

Generated UTC: 2026-10-13T12:00:44.155382+00:00

## Scope

Inspected **451** rows where the legacy method supplies an opponent but the corrected full-signature link does not. This is a diagnostic audit, not model selection.

## Findings

- Single-game source rows (gp=1): **445**; multi-game aggregate rows (gp>1), excluded from one-game linkage: **6**.
- Among gp=1 rows, official player-game row on the inferred date: **430**; no row: **15**.
- Among gp=1 rows, source Dunkest team equals official NBA team: **407**; differs: **23**.
- Among gp=1 rows, legacy opponent equals official opponent: **407**.
- Rounded PDK matches official game PDK: **430**; all 17 box-score fields match: **428**.
- Rows with a date-assisted exact PDK+17-stat candidate: **428** (before accepting the approach outside this audit).

### Row classification

| Class | Rows |
|---|---:|
| exact_boxscore_pdk_team_and_opponent_confirmed | 405 |
| NBA_team_differs_from_source_team | 23 |
| no_player_game_record_on_date | 15 |
| multi_game_aggregate_not_single_game | 6 |
| team_and_opponent_confirmed_but_signature_differs | 2 |

### Link-status counts

| Link status | Rows |
|---|---:|
| ambiguous_exact_team_signature | 410 |
| ambiguous_boxscore_pdk_match_without_team | 21 |
| unique_boxscore_pdk_match_nba_team_unknown | 11 |
| <no link row> | 6 |
| unresolved_no_exact_signature | 3 |

## Interpretation

The legacy-only set is heterogeneous. Six rows have gp>1 and represent multi-game aggregates, so they must not receive a single-game opponent link. Of the 445 gp=1 rows, 405 have an exact same-date PDK+17-stat candidate whose official NBA team and opponent agree with the legacy assignment; 23 have exact PDK+17-stat candidates but the official NBA team differs from the source Dunkest team, so the legacy opponent is wrong for that NBA game; two have same-team/date candidates but fail the exact 17-stat signature; and 15 have no official player-game row on the inferred date. Thus, an independent round-date consensus can potentially disambiguate 428 exact PDK+stat signatures (405 same-team and 23 corrected-team links) without weakening the signature rule. This is an audit hypothesis only: date-assisted linking must be implemented and validated as a separate experimental dataset before model use. Absence from this archive does not prove DNP/OUT.

## Artifacts
- Detailed row-level audit: `reports/audit/dunkest_legacy_only_opponent_rows_20261013_v1.csv`
- Counts by season/class: `reports/audit/dunkest_legacy_only_opponent_rows_20261013_v1_summary.csv`
- Machine-readable summary: `reports/audit/dunkest_legacy_only_opponent_rows_20261013_v1.json`

## Guardrails

- Audit-only; no production code, model, labels, temporal splits, or coefficients changed.
- No claim that missing player-game rows mean DNP or OUT; source coverage may be incomplete.
- Historical weekly rows are not treated as pre-lock roster snapshots.
- Frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.
