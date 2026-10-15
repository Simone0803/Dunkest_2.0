# Dunkest — audit MILP vs baseline e validazione multi-giornata
Data: 2026-10-14

## Obiettivo

Verificare se il selettore MILP aggiunge valore rispetto a strategie semplici con gli stessi vincoli e collegare la valutazione multi-giornata a risultati realizzati osservabili. L'audit non modifica i parametri di produzione.

## 1. Confronto per singola giornata

Script: scripts/backtest_dunkest_historical_lineups_lagged_market_v6.py

Sono state ottimizzate 409 giornate storiche con quattro criteri di selezione:
- MILP con previsione walk-forward del modello;
- MILP con media PDK delle ultime cinque giornate;
- MILP con ranking PDK/CR;
- MILP con ranking percentile all'interno del ruolo.

Le quattro strategie condividono il medesimo pool lagged di candidati, budget di 95 CR inclusi 10 CR coach proxy, ruoli 4G/4F/2C, slot, capitano, limite di tre elementi per squadra NBA incluso l'allenatore e impostazioni CBC. Varia soltanto il punteggio usato per selezionare i giocatori.

### Risultati stretti osservati

| Confronto (MILP modello meno baseline) | Giornate con tutti gli esiti osservati | Differenza media | IC bootstrap 95% |
|---|---:|---:|---:|
| Media PDK previous-5 | 2 | +7,285 PDK | [−0,480; +15,050] |
| Ranking PDK/CR | 2 | +73,652 PDK | [+59,925; +87,380] |
| Ranking per ruolo | 2 | +8,320 PDK | [−6,130; +22,770] |

Solo **2 su 409** giornate hanno esiti osservati completi per tutti i giocatori selezionati e per il coach in tutte e quattro le strategie. I risultati sono descrittivi e non hanno potenza sufficiente per dichiarare un vincitore. Il grande gap rispetto al ranking PDK/CR è condizionato da sole due giornate e non va interpretato come un vantaggio generalizzabile.

## 2. Strategia sequenziale multi-giornata

Script: scripts/backtest_dunkest_historical_lineups_sequential_transfer_v3.py

Ogni scenario trasporta la propria rosa raccomandata alla giornata successiva e applica lo stesso malus realizzato di 5 punti per trasferimento. Il parametro variato è soltanto il costo di trasferimento nella funzione obiettivo: 0, 2,5 o 5. I punteggi mancanti non sono imputati a zero. Il confronto paired usa gli stessi round ID per cui ogni scenario ha tutti gli esiti selezionati osservati.

### Risultati stretti osservati

| Confronto | Round paired completi | Differenza media del punteggio netto | IC bootstrap 95% |
|---|---:|---:|---:|
| Penalità obiettivo 2,5 meno 0 | 11 | +10,977 PDK | [+2,001; +22,877] |
| Penalità obiettivo 2,5 meno 5 | 11 | +0,736 PDK | [−0,143; +1,960] |
| Penalità obiettivo 5 meno 0 | 11 | +10,240 PDK | [+0,944; +22,168] |

Il denominatore è **11 round paired completi su 409**. Il sottoinsieme completo potrebbe non essere rappresentativo: una rosa con un solo esito selezionato non osservato viene esclusa. Le differenze possono riflettere la selezione del sottoinsieme, oltre alla strategia. Pertanto gli intervalli bootstrap non eliminano il bias del mercato storico ricostruito e non autorizzano a cambiare il coefficiente di produzione.

## 3. Collegamento agli esiti realizzati e qualità delle prove

- I PDK giocatore derivano dall'archivio storico Dunkest disponibile e sono usati soltanto dopo la selezione per calcolare gli esiti.
- I punteggi coach sono ricostruzioni della componente base da risultati NBA, con coach fissati a 10 CR; non sono punteggi coach ufficiali price-adjusted.
- I prezzi e ruoli sono lagged dalle ultime righe archiviate disponibili, non da snapshot completi pre-lock.
- Il pool storico non include necessariamente nuovi giocatori, assenze dal dataset o cambi squadra senza una riga precedente.
- I risultati di rose complete sono pubblicati soltanto quando gli esiti selezionati necessari sono osservati; gli altri round restano esclusi dal confronto stretto.
- La rosa portata avanti nella simulazione multi-giornata è la raccomandazione precedente del modello, non la rosa storica reale dell'utente.

## 4. Decisione tecnica

1. Non modificare i pesi del modello, risk_lambda o la penalità trasferimenti sulla base di questi risultati.
2. Mantenere i baseline come benchmark permanenti e rigenerarli quando migliora la copertura degli esiti.
3. Usare la pipeline di archiviazione pre-lock e post-match per raccogliere crediti, ruoli, coach, indisponibilità, fixture e risultati con timestamp e hash verificabili.
4. Per certificare la strategia multi-giornata, richiedere un numero sostanziale di round paired completi, una copertura mercato più ampia e risultati coach coerenti con le regole ufficiali.
5. Mantenere il holdout GW1 2026/27 congelato fino al 2026-10-23 12:00 UTC.

## Artefatti

- reports/audit/dunkest_historical_lineups_fair_baselines_20261014_v1.md
- reports/audit/dunkest_historical_lineups_fair_baselines_20261014_v1_rounds.csv
- reports/audit/dunkest_historical_lineups_sequential_transfer_strict_20261014_v1.md
- reports/audit/dunkest_historical_lineups_sequential_transfer_strict_20261014_v1_rounds.csv
- reports/audit/dunkest_lineup_baselines_and_multigameweek_paired_bootstrap_20261014_v1.md

Nessun parametro di produzione modificato. Nessun commit o push eseguito.
