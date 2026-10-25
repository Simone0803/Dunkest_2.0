# Audit: storico individuale e aggiornamento della stagione corrente

Data: 23 ottobre 2026  
Repository: `Dunkest_2.0`  
Branch: `codex/claude-audit-hardening-20261015`

## Esito

La causa del caso Mitchell Robinson era nella pipeline di training: i log NBA della stagione precedente venivano richiesti solo se il flag `use_nba_api_logs` era attivo, mentre quello era disattivato; inoltre la costruzione delle feature non univa in modo affidabile i log correnti e precedenti. Di conseguenza un parquet storico presente sul disco non garantiva che arrivasse al predictor.

Ora, dalla GW2 in poi, il training forza l’aggiornamento dei log NBA, richiede una raccolta completa e valida, unisce le partite correnti a quelle precedenti e ricostruisce le feature rispettando il cutoff della partita target. Le fonti e il numero di gare correnti e precedenti sono esposti nell’output diagnostico. `use_nba_api_logs` è attivo per default; la raccolta sintetica resta disabilitata salvo opt-in esplicito.

## Criticità e correzioni

| Gravità | Causa/evidenza | Correzione | Verifica |
|---|---|---|---|
| Alta | Log 2025-26 presenti ma non caricati nel flusso GW2; il manifest GW2 indicava `use_nba_api_logs=false` e cache 2026-27 vuota. | Refresh post-GW1 e merge dei log correnti e precedenti prima della costruzione feature. | Test GW1→GW2→GW3; replay diagnostico Robinson. |
| Alta | La cache poteva essere rimpiazzata da una raccolta vuota/parziale o non corrispondente a tutti i giocatori richiesti. | Validazione delle entità richieste, chiavi non nulle e univoche; una risposta incompleta non sovrascrive dati validi. Raccolta completa vuota è ammessa all’inizio stagione, ma conserva le gare già salvate se la cache era popolata. | Test di raccolta vuota completa, preservazione delle gare e risposta incompleta. |
| Media | Il predictor non rendeva esplicita la provenienza della cronologia. | Aggiunti conteggi di storico precedente e disponibile prima del target e `history_source`. | Test sui campi d’output e sulle fonti. |
| Media | I test di freschezza e raccolta post-partita dipendevano da date ormai trascorse. | Aggiornati i fixture temporali e congelato l’orologio nel test post-partita. | Suite completa. |

## Aggiornamento progressivo e forma

Prima di addestrare/prevedere dalla GW2 in poi, la pipeline forza il fetch NBA dei game log. Una raccolta completa viene salvata in `data/processed/player_game_logs_<stagione>.parquet` e unita alla cache completa precedente usando `PLAYER_ID` + `GAME_ID`: le gare già viste vengono aggiornate, quelle nuove aggiunte e quelle precedenti non restituite dall’API conservate. Chiavi duplicate o mancanti fanno fallire la validazione. La feature engineering usa solo gare antecedenti alla data target, quindi la forma aggiornata entra nelle giornate successive senza includere partite future.

Il refresh dipende dalla disponibilità della fonte pubblica NBA; un errore o una risposta incompleta è esplicito e non sostituisce la cache valida. È possibile disabilitare la raccolta impostando `use_nba_api_logs: false`; in tal caso non si ottiene l’aggiornamento automatico. Questa funzione conserva i box score NBA per aggiornare la forma; i label PDK ufficiali Dunkest restano distinti e possono non essere disponibili per ogni partita.

## Robinson: confronto prima/dopo

| Indicatore | Run GW2 originale | Replay diagnostico con storico collegato |
|---|---:|---:|
| `has_history` | `false` | `true` |
| Gare di storico | 0 | 60, stagione 2025-26 |
| `expected_min` | circa 18,72 | circa 22,65 |
| `pdk_rate_for_projection` | circa 1,556, fallback mercato | circa 0,917, prior da stagione precedente |
| `expected_pdk` | circa 29,14 | circa 20,92 |
| `historical_pdk_per_min` ufficiale | NaN | NaN |

Il replay ha usato i log reali presenti e ha confermato il percorso storico fino al predictor, ma una riga mercato/schedule ricostruita e uno stub del modello: non è un nuovo forecast integrale controllato né una misura di miglioramento. Il valore ufficiale PDK rimane NaN se manca il label Dunkest corrispondente; non viene riempito artificialmente.

## Test e riproduzione

Eseguito l’intero test suite:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q
```

Risultato: **650 passed**, 1 warning non bloccante di `joblib` nel rilevamento dei core fisici. Il controllo del diff (`git diff --check`) è pulito.

I test pertinenti coprono: storico precedente anche con cache corrente vuota; propagazione al predictor; incremento sintetico GW1→GW2→GW3; idempotenza e upsert; raccolta completa vuota senza cancellare gare già persistite; rifiuto di risposte incomplete; refresh forzato post-GW1; cutoff temporale.

## Verifiche non certificabili e limiti residui

- Il file GW2 iniziale non era un input snapshot pre-lock certificato e la cache 2026-27 era vuota. Non è quindi possibile certificare un backtest prospettico riproducibile o confrontare due run completi sugli stessi input.
- Non è stato eseguito un backtest walk-forward completo 2018/19–2025/26, né si riportano MAE/RMSE: questo report non ha verificato che tutti i target ufficiali e gli snapshot temporali necessari siano presenti e abbinabili.
- Non è stato eseguito un nuovo forecast integrale con API NBA e roster/quote/availability pre-lock verificati; il replay Robinson è un controllo del flusso, non una previsione di produzione.
- La qualità dei PDK ufficiali, delle disponibilità timestampate, dei coach e del punteggio finale delle formazioni richiede una validazione separata con snapshot e regole ufficiali per ogni giornata.

Nessun outcome GW1 è stato usato per calibrare pesi o coefficienti. Non sono stati creati commit.

Le verifiche successive su forecast reale, backtest e formazioni sono documentate nel [report della Fase 2](phase2_end_to_end_validation_20261023.md).
