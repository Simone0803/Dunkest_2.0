# Dunkest official validity rule and historical flag audit v1

## Official sources

1. [Calendario Dunkest NBA: squadre a riposo e punteggi medi](https://www.dunkest.com/it/nba/notizie/fantabasket/18229/calendario-dunkest-nba-squadre-valide-punteggi-medi) — La giornata fantasy NBA può durare più giorni; se una squadra ricompare nella stessa giornata, conta una sola partita e non necessariamente la prima in ordine cronologico. La squadra non valida non prende punteggio. L’articolo dichiara che il calendario completo è disponibile nella sezione Calendario dell’app.
2. [Calendario Dunkest: la Giornata e i Turni di Gioco](https://www.dunkest.com/it/notizie/fantabasket/8774/calendario-dunkest-cosa-sono-giornata-turni) — Conferma che le giornate NBA Dunkest coprono un numero variabile di giorni e che, se una squadra compare più volte, soltanto una partita attribuisce punti.

## Archived flag consistency

| Season | Team-games | True | False | Mixed flags within team-game | False-flag player rows with PDK / total false rows |
|---|---:|---:|---:|---:|---:|
| 2018-19 (ID 1) | 2,460 | 0 | 2,460 | 0 | 26,094 / 26,094 |
| 2023-24 (ID 13) | 2,460 | 1,812 | 648 | 0 | 6,805 / 6,805 |
| 2024-25 (ID 19) | 2,460 | 1,878 | 582 | 0 | 6,041 / 6,041 |
| 2019-20 (ID 3) | 2,118 | 0 | 2,118 | 0 | 22,384 / 22,384 |
| 2020-21 (ID 5) | 2,160 | 1,689 | 471 | 0 | 4,906 / 4,906 |
| 2021-22 (ID 7) | 2,460 | 1,851 | 609 | 0 | 6,001 / 6,001 |
| 2022-23 (ID 9) | 2,460 | 1,866 | 594 | 0 | 6,100 / 6,100 |

## Interpretation

- Official Dunkest documentation establishes the intended product rule: a team can have multiple NBA games in one Dunkest fantasy matchday, but only one game is eligible to contribute points; the eligible game is not necessarily the first chronologically.
- For seasons 2020/21 through 2024/25, archived game-level flags are consistent across players within every matched team-game, and false-flag player rows still have PDK values. This is consistent with false meaning “this NBA game does not count for Dunkest scoring,” not “the score is missing or zero.”
- For seasons 2018/19 and 2019/20, every archived flag is false. This is inconsistent with using the field as a reliable valid/invalid discriminator in those seasons; treat it as legacy/unverified rather than evidence that every game was excluded.
- The documentation explains the rule but does not publish a downloadable historical round-to-date mapping. Therefore it validates the conceptual meaning, not a complete row-by-row reconstruction of historical fantasy rounds.

## Decision and safeguards

Keep the raw flag and official PDK unchanged. Continue strict training only on gameValidForDunkest=True for seasons where the flag is populated with both true and false values and the existing audit policy permits use (2020/21 onward). Do not reinterpret 2018/19 or 2019/20 as valid targets without independent historical evidence.

- No raw data, target, model, split, or backtest files modified.
- No reconstructed proxy substituted for official PDK.
- This audit does not establish historical round boundaries or exception handling for postponed games.

