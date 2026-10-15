# Audit output run Dunkest — 20261012T150816Z_2c74817c

- **Run ID:** `20261012T150816Z_2c74817c`
- **Timestamp:** 2026-10-12T15:08:16.583827+00:00
- **Git branch / commit:** `main` / `14fa06eee6c920e123d75776b118d90bbdce6485`
- **Target:** season 2026-27, gameweek 1
- **Target training:** `auto`; model `ensemble`
- **Market age setting:** 6.0 hours

## Esito sintetico

La run è stata completata con exit code 0 e ha prodotto i quattro Parquet principali e il manifest. Questo conferma l’esecuzione della pipeline, non l’accuratezza predittiva futura.

## Controlli superati

- Predizioni: **552 righe**, 552 nomi unici, nessun duplicato per nome; 30 squadre.
- Coach: **30 righe**, 30 squadre uniche, nessun duplicato per squadra e nessuna proiezione coach mancante.
- Mapping fixture: **16 partite**, tutte `mapping_verified=True` e `fantasy_eligible=True`; copertura delle 30 squadre.
- Mercato: ogni giocatore nelle tre rose si riconcilia con il mercato salvato; nessuna squadra discordante e nessun costo mancante.
- Vincoli rose: 10 giocatori ciascuna, 5 titolari per turno, modulo coerente con i ruoli per tutti i turni; capitano nel proprio turno; limite di 3 giocatori per squadra rispettato anche aggiungendo il coach.
- Budget ricalcolato da crediti giocatori + coach: Rosa 1: 94.5/95 CR, Rosa 2: 95.0/95 CR, Rosa 3: 95.0/95 CR.
- Giocatori selezionati presenti negli snapshot injury e availability con stato problematico: **0** record injury e **0** record availability.

## Rose generate

| Rosa | PDK attesi | Giocatori | Coach | Capitano | Crediti ricalcolati |
|---:|---:|---|---|---|---:|
| 1 | 195.1 | 10 | Ime Udoka (9.0 CR) | Anthony Davis (turno 2) | 94.5/95 |
| 2 | 194.3 | 10 | Micah Nori (7.5 CR) | Jaylen Brown (turno 1) | 95.0/95 |
| 3 | 193.2 | 10 | Jamahl Mosley (6.5 CR) | Walker Kessler (turno 2) | 95.0/95 |

### Moduli verificati per turno

| Rosa | Turno 1 | Turno 2 | Turno 3 |
|---:|---|---|---|
| 1 | 2-2-1 | 2-1-2 | 1-2-2 |
| 2 | 2-2-1 | 2-1-2 | 2-2-1 |
| 3 | 2-2-1 | 2-1-2 | 3-1-1 |

## Diagnostica delle proiezioni

- Stato giocatori: {'Available': 479, 'GAME TIME DECISION (75%)': 71, 'Out': 2}.
- Fonte della proiezione: {'player_history': 460, 'college_rookie_prior': 50, 'no_history': 42}.
- PDK attesi pari a zero: **157/552** (28.4%); tra questi 104 hanno storico e 53 non hanno storico.
- Righe senza storico: **90**; di queste 50 usano il prior rookie/college e 42 hanno fonte `no_history`.
- `cr_market_pdk_per_min` e `cr_market_minutes_per_game` sono nulli per tutte le 552 righe. Queste colonne non stanno contribuendo in questa run; non significa da solo che la previsione finale sia nulla, ma è un elemento da documentare nel successivo audit del modello.
- Le proiezioni a zero non sono automaticamente errori: il modello azzera minuti quando la competizione di ruolo esaurisce la capacità minuti della squadra, e i giocatori senza un tasso PDK affidabile possono avere proiezione zero. Tuttavia, il numero elevato di zeri merita una verifica separata prima di interpretare la classifica completa come previsione affidabile.

## Limiti e cautele

- La run è per la giornata 1 della stagione 2026/27 e precede l’inizio della regular season NBA; gli output sono previsioni, non risultati osservati.
- La validazione strutturale conferma vincoli e coerenza dei dati d’ingresso, ma non prova che le rose NBA/ruoli o le proiezioni riflettano accuratamente le rotazioni che saranno effettive alla data delle partite.
- Il mercato usato è quello già in cache: la configurazione consente una cache fino a 6 ore. Per una decisione reale va aggiornato e ricontrollato il mercato prima delle partite.
- Nessun dataset originale, configurazione, modello o backtest è stato modificato. Questo audit è solo diagnostico.

## File della run

`data/predictions/20261012T150816Z_2c74817c/` contiene `lineups.parquet`, `predictions.parquet`, `coach_predictions.parquet`, `opening_market.parquet`, `manifest.json` e snapshot pre-partita.

## Derivati creati da questo audit

- `reports/audit/dunkest_run_predictions_20261012T150816Z_2c74817c_v1.csv` — predizioni in CSV, ordinate per PDK atteso, con flag di selezione e campi di mercato.
- `reports/audit/dunkest_run_lineups_20261012T150816Z_2c74817c_v1.csv` — rose in CSV con ruolo/costo del mercato e assegnazioni per turno.
- `reports/audit/dunkest_run_output_audit_20261012T150816Z_2c74817c_v1.md` — questo report.
