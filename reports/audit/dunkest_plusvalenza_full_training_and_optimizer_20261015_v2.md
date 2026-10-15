# Plusvalenza: addestramento completo e integrazione nell'ottimizzazione — V2

Generated UTC: 2026-10-15

## Cosa è stato corretto

Il modello finale di plusvalenza viene ora addestrato su **tutte le righe ufficiali valide** delle stagioni verificate. Non viene più escluso un punteggio Dunkest negativo: i punteggi negativi sono risultati reali e informativi per apprendere le perdite di crediti.

Per ogni riga storica la feature prezzo è ricostruita come:

`CR_start = CR_end - plusvalenza`

Il fit finale usa l'intero campione dopo i controlli di validità. Il campionamento ogni quinta giornata resta esclusivamente una scelta della validazione walk-forward per stimare l'errore out-of-sample; non limita il dataset usato nel fit finale.

## Copertura ufficiale effettivamente usata

- Righe ufficiali sorgente: 93.744.
- Righe effettivamente usate nel fit finale: **93.744 (100%)**.
- Punteggi PDK negativi mantenuti: 6.118.
- Stagioni verificate: 2020/21, 2021/22, 2022/23, 2023/24, 2024/25.
- Giornate con dati per stagione: ID 5 = 59; ID 7 = 64; ID 9 = 64; ID 13 = 62; ID 19 = 64.
- Totale coppie stagione-giornata: 313, senza buchi interni nelle sequenze archiviate.
- Copertura NBA: 30 squadre per ognuna delle cinque stagioni.
- Non sono state ricostruite giornate mancanti né usati dati prospettici 2026/27.

Il vecchio archivio conteneva 6.118 righe con PDK negativo che venivano escluse dal filtro `pdk >= 0`. Il filtro è stato rimosso; i campi numerici mancanti e i prezzi iniziali non positivi restano esclusi per ragioni di validità.

## Validazione walk-forward a parità di righe e split

Confronto sul medesimo archivio di 93.744 righe e gli stessi split temporali:

| Feature prezzo storica | MAE ΔCR | Baseline MAE |
|---|---:|---:|
| CR finale (feature precedente, leakage) | 0,072639 | 0,181359 |
| **CR iniziale ricostruito** | **0,062556** | 0,181359 |

La ricostruzione del prezzo iniziale riduce il MAE del 13,9% rispetto alla feature basata sul prezzo finale. La validazione walk-forward valuta 18.467 osservazioni; il modello finale viene poi riaddestrato su tutte le 93.744 righe.

Calibrazione sequenziale gain/flat/loss:
- Osservazioni valutate: 16.795.
- Bias della probabilità di guadagno dopo calibrazione: -0,085 punti percentuali.
- Brier multiclass: 0,272406 raw → 0,261014 calibrato.
- Log loss multiclass: 0,604942 raw → 0,485968 calibrato.

## Plusvalenza dentro l'obiettivo MILP

La selezione della rosa ora assegna un valore esplicito alla plusvalenza attesa di ciascun giocatore:

`objective = PDK_atteso_corretto_per_slot + shadow_price_CR × Σ plusvalenza_attesa - malus_trasferimenti`

- Quando è misurabile, lo shadow price usa la differenza di punteggio ottimo tra budget corrente e budget aumentato di `capital_gain_budget_delta`.
- Poiché il MILP è discreto, la differenza può essere zero in regioni piatte anche quando il budget è abbondante. Per non ignorare la plusvalenza in questi casi, viene usato un valore conservativo derivato dal listone corrente: il 25% della mediana di `expected_pdk / cr` dei candidati con rapporto positivo.
- La plusvalenza non sostituisce il PDK: è un termine additivo che valuta i crediti futuri e penalizza anche le plusvalenze attese negative.
- Ogni soluzione registra `expected_budget_gain`, `future_budget_value_pdk`, `budget_shadow_price` e `capital_gain_shadow_price_method`. I campi sono inclusi anche in `lineups.parquet`.

Il valore di fallback è una proxy prudenziale, non una regola ufficiale Dunkest: per scegliere il peso ottimale servirà una validazione strategica walk-forward con input pre-lock verificati. Non è stato calibrato sul test prospettico GW1 2026/27.

## File modificati

- `src/dunkest/models/capital_gain.py`
- `src/dunkest/optimize/milp.py`
- `src/dunkest/report/artifacts.py`
- `tests/test_role_minutes_projection.py`
- `tests/test_optimizer_smoke.py`

Nessun commit, push, staging o cleanup distruttivo.
