# Audit del possibile bias di ruolo nelle plusvalenze — V1

**Data UTC:** 2026-10-15
**Ambito:** audit descrittivo e walk-forward storico; nessuna modifica ai pesi del modello sulla base della G1 prospettica.

## Sintesi

La tabella delle migliori plusvalenze della cattura G1 mostrava 6 centri nelle prime 8 posizioni. È una concentrazione da verificare, ma non dimostra da sola un bias: la tabella ordina la **plusvalenza attesa assoluta in CR**, non la plusvalenza per credito né il valore complessivo della rosa.

Il convertitore storico di plusvalenza non usa il ruolo come feature: usa PDK realizzato e CR iniziale ricostruito. Quindi non esiste una preferenza esplicita per i centri nel modello di conversione. Il divario osservato nasce dal pool di previsioni PDK/CR e dalla relazione storica fra PDK e ΔCR.

## Evidenza sulla pool G1 già prodotta

Fonte: `data/predictions/20261015T085954Z_9e338bce/predictions.parquet` (541 giocatori).

| Ruolo | Giocatori | Quota pool | PDK/CR medio previsto | ΔCR medio previsto | Quota con ΔCR previsto > 0 |
|---|---:|---:|---:|---:|---:|
| C | 79 | 14,6% | 1,115 | -0,0768 | 13,9%* |
| F | 219 | 40,5% | 0,832 | -0,0832 | 1,8% |
| G | 243 | 44,9% | 0,813 | -0,0935 | 2,5% |

*La metrica della quota positiva è calcolata sulle righe con previsione ΔCR valida (78 centri); una riga del ruolo C non aveva previsione di plusvalenza valida.

Le prime otto righe ordinate per ΔCR atteso erano: 6 C, 1 F e 1 G. I centri in cima hanno anche PDK/CR previsto elevato (circa 2,19–2,54 per i sei centri nei top 8), quindi la concentrazione segue in larga misura le previsioni di produzione rispetto al prezzo. Le probabilità previste di guadagno per questi candidati erano circa 55–68%: sono stime, non garanzie.

## Controllo storico out-of-fold

Archivio: `data/processed/plusvalenza_history_multiseason_26_pre_gw0_5y_nba_v4.parquet`. Split expanding-origin walk-forward, stessi split del convertitore di produzione, 18.467 osservazioni out-of-fold. Residuo definito come **ΔCR realizzato − ΔCR previsto**; valori negativi indicano sovrastima.

| Ruolo | N OOF | ΔCR realizzato medio | Frequenza di guadagno realizzata | MAE | Bias residuo medio |
|---|---:|---:|---:|---:|---:|
| C | 2.894 | +0,0295 | 40,4% | 0,0687 | -0,0181 |
| F | 7.098 | +0,0083 | 34,7% | 0,0609 | -0,0137 |
| G | 8.475 | +0,0155 | 36,1% | 0,0618 | -0,0067 |

Il modello sovrastima mediamente la ΔCR in tutti i ruoli, con una sovrastima storica un po' più ampia per C rispetto a G (differenza di circa 0,0114 CR per giocatore/giornata). Tuttavia il divario non è stabile per stagione: nelle prime tre stagioni OOF i residui per ruolo sono vicini a zero, mentre gran parte della sovrastima è concentrata nelle ultime due stagioni e interessa anche F e G. Questo suggerisce drift temporale/calibrazione generale, non una prova sufficiente di un bias strutturale specifico dei centri.

## Verifica di una correzione per ruolo

È stata simulata una correzione walk-forward relativa al bias medio globale, usando solo residui OOF precedenti e shrinkage di 300 osservazioni. Risultato:

- MAE base: **0,062559 CR**.
- MAE con correzione relativa per ruolo: **0,062572 CR**.
- Miglioramento medio di MAE (base meno corretto): **-0,000012 CR**.
- Intervallo bootstrap appaiato al 95% dell'effetto sulla MAE: **[-0,000053; +0,000027] CR**, include zero.

La correzione relativa per ruolo non migliora la MAE in modo misurabile. **Non viene quindi introdotto un peso o una penalità specifica per i centri**: sarebbe una modifica non supportata dall'evidenza e rischierebbe di degradare la selezione.

## Decisione e limiti

1. Mantenere l'obiettivo attuale: ΔCR attesa assoluta è la metrica corretta se l'obiettivo è accumulare crediti, senza imporre quote artificiali per ruolo.
2. Non interpretare la tabella top-8 come graduatoria di PDK o come raccomandazione completa di rosa.
3. La correzione per ruolo non viene adottata; il follow-up corretto è continuare a misurare calibrazione e residui per stagione/ruolo sullo storico, senza usare la G1 prospettica congelata.
4. Questo audit non certifica il risultato finale della rosa: gli snapshot storici pre-lock completi necessari per un backtest end-to-end restano un requisito separato.
