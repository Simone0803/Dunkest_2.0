# Dunkest complete-lineup backtest readiness audit — V2

Generated (UTC): 2026-10-12T17:41:39.652232+00:00

## Summary

- Season IDs scanned: 26
- Round records scanned: 1
- Rounds ready for full-lineup backtest: **0**
- Rounds not ready: 1

| Input evidence | Rounds passing |
|---|---:|
| fixture mapping | 1/1 |
| roster and CR | 1/1 |
| timestamped injuries | 1/1 |
| fixture linked coaches | 1/1 |
| player results linked | 0/1 |
| coach results linked | 0/1 |

## Round-level status

| Season ID | GW | Mapping | Roster/CR | Injuries | Coaches | Player results | Coach results |
|---:|---:|---|---|---|---|---|---|
| 26 | 1 | OK | OK | OK | OK | missing/invalid | missing/invalid |

## Interpretation

No scanned round has all required archived inputs. Valid complete-lineup metrics cannot be computed without inventing pre-game state or using look-ahead data.

The production command was run for season 2025-26, GW1–10. It returned Backtest non pronto — nessuna metrica lineup prodotta because fixture mapping, roster/CR snapshots, timestamped injury snapshots, fixture-linked coach snapshots and linked player/coach outcomes are missing or unproven.

Historical weekly archives contain round outcomes but do not establish which prices, injuries, availability and coach market were known before tip-off. Using same-round data would introduce look-ahead bias.

## Required capture for future rounds

For each upcoming gameweek, retain an immutable pre-match bundle with: verified fixture mapping (source, retrieval time and payload hash); full player roster and CR; timestamped injuries/availability; coach market linked to NBA fixture IDs; and model predictions generated before tip-off. After games finish, append realized player and coach scores linked to those same fixture IDs. Version every recapture and never overwrite raw snapshots.

## Reproducibility

    PYTHONPATH=$PWD/src ./.venv/bin/python scripts/audit_dunkest_lineup_backtest_readiness_v1.py
