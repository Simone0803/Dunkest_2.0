# Task 14 — Preparazione archivio prospettico appaiato HGB/produzione

**Verificato:** 2026-10-24 08:44 UTC  
**Esito acquisizione live:** bloccata da errore DNS generale; nessun forecast o manifest reale creato.

## Componenti riutilizzati e modifiche locali

È stato esteso il percorso già esistente, senza introdurre una seconda pipeline:

1. `predict_players` conserva, solo come metadato, la riga runtime pre-partita usata dal predictor e la matrice numerica esatta passata all’HGB dopo conversione, sostituzione di infiniti, mediane salvate e zero-fill. Sono esclusi i campi target/post-partita. Il calcolo delle previsioni non è cambiato.
2. `run_predict` passa quel contenuto all’archiviatore insieme all’universo completo `candidate_forecasts`.
3. `save_run_artifacts` produce `runtime_feature_snapshot.parquet`: una riga per ogni record candidato con ID Dunkest/canonico, `forecast_record_id`, partita, cutoff, stato dell’associazione e feature grezze disponibili; quando HGB è disponibile registra anche le colonne trasformate `hgb_input__*`. I candidati senza feature restano presenti con stato `missing`; associazioni ambigue non vengono risolte arbitrariamente.
4. Il manifest lega il file al suo SHA-256, alla versione/codice, alle colonne del modello, ai parametri e target HGB, e all’identificativo dell’insieme input. Include provenienza per input (percorso, hash, `fetched_at`, fonte). Il file viene scritto una sola volta nel nuovo run immutabile.
5. Lo snapshot pre-match ora include anche il parquet del mercato Dunkest effettivamente usato. L’archiviatore richiede e verifica il nuovo file, la copertura di tutti i record candidati, unicità degli ID, collegamento HGB-feature, matrice trasformata finita, hash e provenienza. Il reviewer indipendente ricontrolla anche l’hash registrato nel registry.

I minuti ibridi e HGB restano prodotti dalla stessa chiamata runtime e vengono congelati nella tabella esistente `player_forecast_snapshot.parquet`. I componenti e le decisioni intermedie del ramo ibrido rimangono nel record candidato; il nuovo file documenta la riga feature condivisa e l’esatto input trasformato HGB. Le previsioni mancanti mantengono stati espliciti.

## Verifiche locali

- Il training storico Task 12 aveva 23 delle 68 colonne `FEATURE_COLS` correnti: il replay storico non diventa per questo un replay della produzione.
- Il test runtime ricostruisce l’input HGB dal nuovo snapshot e verifica che `model.predict` riproduca `expected_min_model_shadow` archiviato.
- Il test di salvataggio usa due candidati: uno con feature/HGB appaiati e uno senza feature/HGB. Entrambi restano nello snapshot e sono classificati distintamente.
- Il test di integrità rifiuta una feature la cui disponibilità è successiva al forecast e verifica la mutazione del file tramite hash.
- Le verifiche esistenti coprono cutoff ufficiale, fixture/turno, identità univoche, leakage, immodificabilità dell’archivio, idempotenza di riconciliazione, distinzione zero verificato/mancante e metriche appaiate riproducibili.

**Copertura sintetica:** 2 record candidati conservati, 1 feature row associata, 1 assenza feature/HGB esplicita. Non è copertura di una cattura reale.

## Cutoff e acquisizione prospettica

Alle **2026-10-24T08:44:36Z** una singola verifica DNS ha fallito sia per `example.com` sia per `fantaking-api.dunkest.com` (`socket.gaierror: [Errno 8] nodename nor servname provided, or not known`). Non essendoci risoluzione per il dominio ufficiale, non è stata inviata la richiesta HTTP al calendario. Questa prova indica un blocco DNS dell’ambiente, non una risposta incompleta dell’API.

Non è stato possibile identificare da una fonte aggiornata una giornata/turno futuro e il relativo cutoff. Non è stato avviato il forecast; non c’è un run reale da certificare e gli archivi GW1 precedenti non sono stati modificati o ricertificati. Nessun risultato reale è stato aggiunto al pool di valutazione.

## Riconciliazione ed esiti

Il collector post-partita esistente continua a usare gli ID/fixture verificati e stati distinti per apparizione, zero supportato, DNP, esito mancante/ambiguo. La nuova tabella runtime resta collegata al `forecast_record_id`; l’archiviazione immutabile ne conserva hash e contenuto. Non sono stati acquisiti esiti nuovi. Il confronto HGB-vs-ibrido resta insufficiente per una valutazione walk-forward: il precedente GW1 aveva un unico forecast origin, manifest non eleggibile, 289 record appaiati su 528 candidati e nessuno zero minuti verificato.

## Test

Comando eseguito:

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_role_minutes_projection.py \
  tests/test_prediction_fixture_propagation.py \
  tests/test_artifact_manifest.py \
  tests/test_prelock_archive.py \
  tests/test_dunkest_cutoff_evidence.py \
  tests/test_post_match_collection.py \
  tests/test_minutes_comparison.py
```

Esito: **89 passed** (un warning dell’ambiente joblib sul conteggio dei core fisici). `py_compile` e `git diff --check`: superati; nessun commit o push.

## Limiti e condizione per la valutazione

L’infrastruttura locale ora conserva una matrice feature runtime appaiata a ogni record candidato e la sua provenienza verificabile; non certifica in assenza di cutoff e fonti live. Le righe senza feature o previsione HGB sono conservate ma non entrano nelle metriche appaiate. L’impatto PDK resta non valutato.

Per iniziare il confronto walk-forward servono: risoluzione DNS e accesso in lettura all’endpoint ufficiale, calendario con fixture/cutoff verificabili, una cattura reale completata prima del cutoff e più giornate certificate con esiti riconciliati, inclusi zero/DNP documentati. Fino ad allora la copertura reale Task 14 è **zero giornate**.

## File interessati

- Produzione con soli metadati aggiunti: `src/dunkest/models/predictor.py`, `src/dunkest/pipeline/predict.py`, `src/dunkest/report/artifacts.py`.
- Conservazione/verifica dell’archivio: `scripts/archive_dunkest_pre_lock_run_v1.py`, `scripts/review_dunkest_pre_lock_archive_v1.py`.
- Regressioni verificate: `tests/test_role_minutes_projection.py`, `tests/test_prediction_fixture_propagation.py`, `tests/test_artifact_manifest.py`, `tests/test_prelock_archive.py`, `tests/test_dunkest_cutoff_evidence.py`, `tests/test_post_match_collection.py`, `tests/test_minutes_comparison.py`.
