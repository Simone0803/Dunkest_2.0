# Dunkest source-recovery inventory

Generated UTC: 2026-10-14T20:57:16.295515+00:00
Read-only filename and sidecar scan of data/raw, data/processed, data/predictions, data/archives and data/workspaces.
This audit does not certify any file as pre-lock evidence.

## Candidate files by family

| Family | Files |
|---|---:|
| coach_market_or_outcomes | 139 |
| fixture_mapping | 70 |
| historical_week_round_stats | 2315 |
| injury_or_availability | 161 |
| lineup_or_fixture_calendar | 138 |
| official_player_outcomes | 52 |
| player_market_or_credits | 262 |

## Evidence classes

| Classification | Files |
|---|---:|
| archive_candidate_requires_independent_review | 9 |
| outcomes_or_stats_not_prelock_market | 2367 |
| round_candidate_cutoff_proof_missing | 114 |
| season_or_round_ambiguous | 647 |

## Public sources reviewed

- Dunkest listone article: https://www.dunkest.com/it/nba/notizie/fantabasket/17211/asta-fantabasket-listone-dunkest-nba
- Example player page with PDK and game statistics: https://www.dunkest.com/it/giocatore/126/donte-divincenzo
- Season highlights with selected PDK results, not a complete round archive: https://www.dunkest.com/it/nba/notizie/fantabasket/190007/le-migliori-prestazioni-dunkest-della-stagione-nba-2023-24
- Scoring rules: https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-giocatori and https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-allenatori

## Interpretation

Outcome/stat files can support prediction evaluation but do not prove which market, credit, role or injury information was available before lock.
A fetched_at timestamp records local acquisition; it is not proof of the source's original publication time or the historical lock cutoff.
Do not fill missing historical market data with current pages or reconstructed injury/transfer state.
Prospective archives remain eligible only after intact hashes, fresh snapshots, verified fixture identity and independent review.

Machine-readable inventory: reports/audit/dunkest_source_recovery_inventory_20261014_v1.csv
