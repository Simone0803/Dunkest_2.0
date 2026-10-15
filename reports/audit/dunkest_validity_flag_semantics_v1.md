# Audit semantica `gameValidForDunkest`

Creato: 2026-10-12T11:55:48.887696+00:00

Pagina profilo: https://www.dunkest.com/it/giocatore/127/luka-doncic

Endpoint partite: `https://www.dunkest.com/api/player/games`

## Evidenza dal frontend pubblico

- Etichetta del filtro: **Solo partite valevoli per Dunkest**
- Il codice del frontend scarta una riga quando il filtro è attivo e `gameValidForDunkest === false`. Non contiene una spiegazione della regola che genera il flag.

## Distribuzione per stagione

| Stagione | Righe | Giocatori | Partite API | True | False | PDK presente su False | Partite all-true | all-false | miste | Giocatori con entrambi i flag |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2018-19 | 26094 | 530 | 1230 | 0 | 26094 | 26094 | 0 | 1230 | 0 | 0 |
| 2019-20 | 22384 | 529 | 1059 | 0 | 22384 | 22384 | 0 | 1059 | 0 | 0 |
| 2020-21 | 22568 | 500 | 1080 | 17662 | 4906 | 4906 | 749 | 140 | 191 | 490 |
| 2021-22 | 24424 | 492 | 1230 | 18422 | 6002 | 6002 | 806 | 185 | 239 | 477 |
| 2022-23 | 25265 | 482 | 1230 | 19165 | 6100 | 6100 | 824 | 188 | 218 | 477 |
| 2023-24 | 25732 | 512 | 1230 | 18927 | 6805 | 6805 | 799 | 217 | 214 | 505 |
| 2024-25 | 25631 | 509 | 1230 | 19590 | 6041 | 6041 | 840 | 192 | 198 | 507 |
| 2025-26 | 27706 | 527 | 1305 | 21889 | 5817 | 5817 | 924 | 172 | 209 | 516 |

## Campione live: Luka Dončić

| Stagione | Partite | True | False |
|---|---:|---:|---:|
| 2018-19 | 72 | 0 | 72 |
| 2019-20 | 61 | 0 | 61 |
| 2020-21 | 66 | 51 | 15 |
| 2024-25 | 50 | 39 | 11 |
| 2025-26 | 64 | 50 | 14 |

## Interpretazione operativa

- The endpoint returns non-null PDK values for many rows marked false; false is a validity/filter flag, not a missing-score indicator and must not be replaced with zero.
- The profile UI applies the flag as a display filter, but neither its label nor its filtering code defines the business rule that sets the flag.
- All collected rows for seasons 2018/19 and 2019/20 are false; therefore the strict valid-target policy yields zero target rows from those seasons. This alone does not prove their PDK numbers are arithmetically wrong, but their official Dunkest-game eligibility cannot be established from this flag.
- In later seasons, true and false can coexist for a single Dunkest gameId and for a single player across different dates. Thus the flag is not merely a season-level indicator.
- Keep raw PDK and raw flag, keep the current strict target selection for seasons with true flags, and exclude 2018/19–2019/20 from strict official-target training unless an independent historical round/calendar source verifies eligibility. No model or split was changed.

## Archivi storici di round disponibili

| Season ID | File avg per settimana/round |
|---:|---:|
| 13 | 154 |
| 16 | 29 |
| 19 | 158 |
| 22 | 35 |
| 25 | 5 |

Nessun target, modello, split o file di produzione è stato modificato.
