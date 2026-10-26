# Audit persistenza forecast operativi PDK — 2026-10-26

## Sintesi

La pipeline ordinaria produce già snapshot versionati per candidati, feature runtime, minuti shadow e coach. Il run reale più recente esaminato è `20261025T101251Z_6d20853d`. Contiene previsioni e provenienza sufficienti per analisi diagnostiche limitate, ma il manifest lo marca correttamente `incomplete` e `pre_lock_eligible=false`: 148/519 candidati non hanno l'ID Dunkest, mentre 87 righe non hanno una feature runtime abbinata e 2 hanno un abbinamento ambiguo. Il run non ha inoltre `archive_manifest.json` né una registrazione nel registry immutabile; non è quindi accettato dal flusso di riconciliazione degli outcome.

È stata aggiunta una protezione minima perché la scrittura per run fosse append-only anche in caso di collisione dell'ID. È stato inoltre aggiunto un controllo fail-closed che impedisce di mettere colonne di outcome realizzato negli input prepartita. Non sono state modificate previsioni, feature, pesi, optimizer o rose.

## Stato iniziale e preservazione

Prima delle modifiche, `git status --short` mostrava già modifiche locali in `src/dunkest/__main__.py`, `src/dunkest/pipeline/predict.py` e test del workflow/roster/cutoff, oltre a file locali non tracciati in `config/`, `graphify-out/`, `reports/audit/`, `scripts/`, `src/` e `tests/`. Tali modifiche sono state lasciate intatte. I due file modificati da questo intervento (`src/dunkest/report/artifacts.py` e `tests/test_artifact_manifest.py`) erano puliti prima della modifica.

## Flusso effettivo e campi

1. `src/dunkest/__main__.py` esegue `run_train`, `run_predict`, `run_optimize`, stampa il report e chiama `save_run_artifacts`.
2. `src/dunkest/pipeline/predict.py::run_predict` crea le proiezioni operative, allega contesto fixture, disponibilità e DvP, conserva i candidati, aggiunge il timestamp forecast e cutoff verificato negli `attrs` e passa al writer lo snapshot runtime prodotto dal predictor.
3. `src/dunkest/models/predictor.py::predict_players` produce minuti operativi, componenti PDK, probabilità di presenza e, se disponibile, minuti HGB shadow con la relativa matrice trasformata. Lo snapshot runtime rimuove le colonne postpartita note.
4. `src/dunkest/report/artifacts.py::save_run_artifacts` crea una directory `data/predictions/<run_id>/`, salva `predictions.parquet`, snapshot candidati, runtime feature, shadow, coach, input prepartita e `manifest.json` con versioni, hash, configurazione e provenienza.
5. `scripts/archive_dunkest_pre_lock_run_v1.py` copia e sigilla il run, verifica gli snapshot e registra l'eligibilità. `scripts/build_dunkest_post_match_results_v1.py` accetta solo un bundle sigillato e certificato. Collega gli outcome Dunkest ufficiali a partita/giocatore tramite fixture verificata, data, squadra/avversario e `player_key`; conserva gli outcome in un archivio postpartita separato senza modificare gli snapshot originari.

Campi effettivamente prodotti e salvati nel contratto corrente: PDK previsto, PDK condizionale, rate, probabilità di presenza, componenti e pesi PDK, minuti previsti, stato/ruolo/contesto, ID partita NBA, turno e ID match Dunkest quando presenti, timestamp forecast e cutoff, versioni/hash codice-configurazione-input. Season e gameweek sono nel manifest/configurazione del run e raggiungibili da ogni record tramite `forecast_run_id`; non sono duplicati come colonne per riga. Il runtime feature snapshot contiene le feature trasformate del modello minuti shadow e le feature sorgente abbinate, non una matrice completa di tutti i passaggi interni del predittore PDK. I componenti PDK salvati consentono di diagnosticare il valore finale senza rifare l'inferenza.

Gli outcome non fanno parte dello snapshot prepartita. Il builder postpartita usa una corrispondenza per `nba_game_id` e `player_key`, con controllo squadra e fixture; gli outcome ufficiali non riconciliati restano mancanti/ambigui, non sono trasformati in zero. Il collegamento ufficiale non usa direttamente l'ID Dunkest del giocatore: la risoluzione si basa sul nome normalizzato e sul mercato congelato.

## Ispezione del run reale

Artefatti ispezionati: `data/predictions/20261025T101251Z_6d20853d/` e il relativo `manifest.json`.

| Artefatto | Righe | Osservazioni |
|---|---:|---|
| `predictions.parquet` | 449 | Vista eleggibile all'optimizer; include `expected_pdk`, `expected_min`, `pdk_rate_for_projection`, `p_play`, ruolo e stato. |
| `player_forecast_snapshot.parquet` | 519 | Universo candidati; ID record univoci; minuti, PDK e componenti disponibili; 148 ID Dunkest mancanti. |
| `runtime_feature_snapshot.parquet` | 519 | 430 feature abbinate, 87 mancanti, 2 ambigue; manifest `incomplete`. |
| `shadow_forecast_snapshot.parquet` | 519 | Minuti shadow salvati separatamente; non sono input dell'optimizer. |
| `coach_forecast_snapshot.parquet` | 29 | Forecast coach e matchup con ID partita, timestamp, cutoff e versione. |

Il forecast è timestampato `2026-10-25T10:12:14Z`, con cutoff `2026-10-25T20:59:00Z`. L'ID modello salvato è `fab4b401c542b474f1469a894ba1a544c1d5fb55`. Gli hash degli snapshot e degli input sono presenti nel manifest. Il manifest riporta `archive_status=incomplete`, `snapshot_set_complete=false`, `candidate_stable_identity_verified=false`, `runtime_feature_snapshot.status=incomplete` e certificazione pre-lock falsa. L'ID canonico di ripiego per i 148 record è il nome normalizzato; non è stato elevato a ID ufficiale. Il campo aggregato `availability_observed_at_utc` è mancante, anche se gli timestamp separati Lineups e injury sono presenti nelle righe.

In `data/archive/26/gw3/` risultano snapshot prepartita di input, ma non un archivio postpartita `post_match_*`; nel run indicato manca anche `archive_manifest.json`. Pertanto non sono state calcolate metriche né dichiarata una raccolta prospettica valutabile.

## Modifiche

- `src/dunkest/report/artifacts.py`: la directory del run viene creata con `exist_ok=False`. Una collisione di run ID ora fallisce prima di scrivere; non può sovrascrivere manifest o forecast già esistenti.
- `src/dunkest/report/artifacts.py`: il writer rifiuta input prepartita che contengano colonne note di target/outcome realizzati (`actual_pdk*`, minuti effettivi, target PDK/minuti, PDK coach effettivo e `outcome_status`). Il controllo avviene prima di creare la directory del run.
- `tests/test_artifact_manifest.py`: test di collisione append-only e test che verifica il rifiuto degli outcome negli input prepartita.

## Verifiche realmente eseguite

- `graphify query "Trace how the live player forecast is built, what artifacts are saved, and whether runtime feature and outcome linkage are preserved" --budget 1800` — usato come indice di navigazione, poi verificato leggendo il codice sorgente.
- Ispezione statica con `rg`, `sed`, `find`, `git status --short` e lettura dei Parquet/manifest tramite `./.venv/bin/python`; nessun forecast, training o scraping eseguito.
- `./.venv/bin/pytest -q tests/test_artifact_manifest.py tests/test_post_match_collection.py` — **40 passed**.
- `./.venv/bin/pytest -q tests/test_prelock_archive.py tests/test_post_match_evaluator.py` — **53 passed**.
- `./.venv/bin/python -m py_compile src/dunkest/report/artifacts.py tests/test_artifact_manifest.py` — completato senza errori.
- `git diff --check` — completato senza errori.

## Limiti e criterio di sufficienza

La raccolta non è ancora completa per diagnosi PDK con attribuzione per coorte: servono run ordinari con snapshot candidati completi e identità stabili, feature runtime abbinate senza ambiguità per i record a cui si applica il modello shadow, archiviazione pre-lock sigillata e outcome Dunkest ufficiali riconciliati in un archivio separato. I campi aggregati mancanti non vanno riempiti retroattivamente. Le stagioni/GW possono restare metadati del bundle, purché l'ID run colleghi senza ambiguità ogni riga al manifest.

Il run GW3 esaminato resta diagnostico e incompleto; non va usato come holdout certificato. La raccolta potrà dirsi avviata quando un nuovo run operativo eleggibile sarà sigillato e i risultati ufficiali postpartita saranno riconciliati sullo stesso `nba_game_id` e identità giocatore senza ambiguità. Una validazione prospettica richiederà inoltre più giornate, copertura dichiarata e un protocollo appaiato; non basta il singolo run.
