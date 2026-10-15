# BOS–CLE validity cross-endpoint check (v1)

- NBA game: BOS–CLE, 2023-12-12.
- Dunkest schedule: schedule 8, matchday 278, match 2440.
- Schedule-level flags: Boston `true`, Cleveland `false`.
- Player-games API: six players queried (three from each team); all six returned `gameValidForDunkest=false` for gameId `8469`.
- Local official archive: all nine Boston player rows and all nine Cleveland player rows are `false` for the same gameId.

| Dunkest player ID | Source team | API gameValidForDunkest | PDK |
|---:|---|---|---:|
| 436 | BOS | `False` | 34.13 |
| 65 | BOS | `False` | 27.04 |
| 212 | BOS | `False` | 24.68 |
| 326 | CLE | `False` | 30.5 |
| 8 | CLE | `False` | 25.5 |
| 606 | CLE | `False` | 30 |

## Conclusion

The two API fields do not agree for this game. The player-games API matches the archived per-player flags, while the schedule endpoint differs for Boston. Do not mutate `gameValidForDunkest` or PDK values based on schedule `is_valid`; retain this as an unresolved cross-endpoint semantic/data discrepancy.
