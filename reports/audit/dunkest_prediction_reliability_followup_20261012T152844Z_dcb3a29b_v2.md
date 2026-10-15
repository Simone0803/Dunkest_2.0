# Follow-up affidabilità previsioni Dunkest — 20261012T152844Z_dcb3a29b

- **Run ID:** `20261012T152844Z_dcb3a29b`
- **Data run:** 2026-10-12T15:28:44.421537+00:00
- **Git commit:** `14fa06eee6c920e123d75776b118d90bbdce6485` (nessun commit effettuato in questo lavoro)
- **Stagione / turno:** 2026-27 / GW1

## Modifiche correttive effettuate

1. **Ripristino del prior storico di mercato.** La pipeline season-opener ora cerca prima il file versionato `dunkest_players_25_gw35.parquet` e, se manca, usa il cache legacy `dunkest_players_gw35.parquet` soltanto se schema e righe PDK/minuti/crediti sono utilizzabili. Lo snapshot non è usato come target ufficiale né sovrascrive il mercato corrente.
2. **Controllo di coerenza dei quintetti.** Prima della previsione, se una squadra ha più di cinque giocatori marcati `QUINTETTO`, il sistema ignora i tag di rotazione per quella squadra e conserva prezzi, team e status. Nello snapshot attuale i conteggi impossibili erano CLE=14 e DEN=13; i tag non sono stati usati per generare le previsioni.
3. **Test di regressione aggiunti** per prior storico versionato/legacy, schema non valido, quintetto impossibile e quintetto valido.

## Esito dei controlli

- 552 previsioni, nomi unici, PDK atteso finito per ogni riga.
- Le colonne `cr_market_pdk_per_min` e `cr_market_minutes_per_game` ora sono valorizzate per **552/552** giocatori; prima erano vuote per tutti.
- Proiezioni PDK pari a zero: **127/552 (23.0%)**, contro **157/552 (28.4%)** nella run originale. È un calo di 30 zeri, ma non è una misura diretta dell’accuratezza predittiva.
- Proiezioni con minuti attesi pari a zero: **127**; questi casi rimangono il prossimo punto diagnostico perché derivano in gran parte dalla competizione/allocazione dei minuti.
- Fonti di proiezione: `{'player_history_shrunk': 460, 'college_rookie_prior': 50, 'cr_market_prior': 40, 'prior_season_player_market_shrunk': 2}`.
- Stati disponibilità: `{'Available': 479, 'GAME TIME DECISION (75%)': 71, 'Out': 2}`.
- Tag di rotazione invalidi CLE/DEN: rimossi dal dataframe passato al modello; lo snapshot grezzo `opening_market.parquet` è conservato senza alterazioni per audit.

## Rose generate dopo la correzione

| Rosa | PDK attesi | Budget | Capitano (turno) | Coach / squadra | Moduli T1 / T2 / T3 |
|---:|---:|---:|---|---|---|
| 1 | 211.5 | 95.0/95 CR | Kyrie Irving (T2) | Micah Nori / POR | 3-1-1 / 3-1-1 / 2-2-1 |
| 2 | 202.2 | 95.0/95 CR | Damian Lillard (T2) | Ime Udoka / HOU | 2-2-1 / 3-1-1 / 1-2-2 |
| 3 | 199.1 | 95.0/95 CR | Jayson Tatum (T1) | Jamahl Mosley / NOP | 2-2-1 / 3-1-1 / 2-1-2 |

## Interpretazione e limiti

- Il run ha completato la pipeline, ma la stagione 2026/27 non è iniziata: non esiste ancora un risultato reale con cui misurare l’errore di queste previsioni.
- Il prior storico ripristinato cambia il livello delle proiezioni e riduce gli zeri, ma questo da solo non dimostra un miglioramento in MAE/RMSE. Per scegliere pesi o modificare l’allocazione minuti servono snapshot prepartita verificati e un backtest walk-forward senza leakage.
- I 127 casi a zero non sono stati forzati a un minimo artificiale: alcuni sono legati alla capacità minuti per squadra/ruolo e all’assenza di informazioni affidabili sulla rotazione corrente. Il CSV allegato li espone per esame, con richieste di minuti, profondità di ruolo, storico e prior mercato.
- Lo snapshot legacy è datato 2026-09-29 e deriva dalla tabella stats Dunkest GW35; il metadata non contiene un campo stagione esplicito. Per questo è usato soltanto come prior debole di PDK/minuti e non come label ufficiale.
- Non sono stati modificati dataset originali, target ufficiali, split temporali, backtest o configurazione di produzione; non è stato creato alcun commit.

## Artefatti

- `reports/audit/dunkest_prediction_zero_diagnostic_20261012T152844Z_dcb3a29b_v1.csv` — elenco completo delle proiezioni a zero.
- `reports/audit/dunkest_prediction_run_comparison_20261012T152844Z_dcb3a29b_v1.csv` — confronto quantitativo tra run originale, ripristino prior e controllo dei tag.
- Output completo della run: `data/predictions/20261012T152844Z_dcb3a29b/`.

## Verifica finale e casi ancora da monitorare

- Suite completa: **218 test superati, 0 falliti**. Restano 6.800 warning, quasi tutti deprecazioni di PuLP/CBC; un test segnala un cache mercato senza metadata di freschezza.
- `git diff --check` e `py_compile` sui moduli modificati completati senza errori.
- Dei 127 zeri residui, 91 hanno prezzo ≤4,5 CR, 29 hanno prezzo >4,5 e ≤6 CR e 7 hanno prezzo >6 e ≤8 CR; nessun giocatore con prezzo >8 CR ha PDK atteso pari a zero.
- I sette casi >6 CR sono Morez Johnson, Brayden Burries, Jordan Goodwin, Keldon Johnson, Aaron Wiggins, Isaiah Stewart e Herbert Jones. Keldon Johnson è marcato Out; quattro giocatori con storico (Goodwin, Wiggins, Stewart, Jones) hanno minuti storici indicativi e vengono azzerati dalla competizione di ruolo/allocazione minuti; i due rookie dipendono dal prior. Questi casi non vanno corretti con un minimo artificiale: richiedono una validazione della regola di allocazione con snapshot prepartita storici verificati.
- Per ora non ho modificato la regola di allocazione dei minuti né i pesi del modello: il progetto non dispone di snapshot storici completi e verificati per dimostrare che una diversa allocazione riduca MAE/RMSE senza leakage. Cambiarla ora potrebbe solo spostare le proiezioni senza provare un miglioramento.

Questa versione aggiorna il report v1 senza sovrascriverlo; i CSV diagnostici citati sopra restano quelli della stessa run.
