# Primo forecast prospettico Dunkest — verifica di acquisibilità

**Verifica:** 2026-10-24 08:09 UTC (10:09 Europe/Amsterdam)  
**Esito:** bloccato prima della previsione; nessun forecast creato e nessun archivio storico modificato.

## Flusso e identità

La verifica del percorso locale conferma che il mercato consegna `id` e `predict_players` lo copia in `dunkest_player_id`. `save_run_artifacts` scrive questo valore nello snapshot insieme a `forecast_run_id`, `forecast_record_id`, `forecast_timestamp_utc`, stato di disponibilità di minuti ibridi/HGB, fixture e cutoff. Il manifest verifica presenza e unicità dell'identità stabile giocatore-partita; l'archiviatore ricontrolla i campi e gli hash. I test locali coprono il passaggio market → predictor → `player_forecast_snapshot.parquet`, più i casi shadow mancante e multi-turno.

Il processo post-partita esistente conserva una riga per candidato e distingue apparizioni, zero minuti esplicitamente verificati, DNP documentato, fixture non verificata e risultato mancante/ambiguo. L'assenza da un log non diventa zero; gli esiti non riconciliabili restano nel pannello. Non essendoci un nuovo run, nessun candidato è ancora riconciliabile per questa acquisizione.

## Calendario, cutoff e blocco

La fonte implementata è l'API ufficiale di calendario usata dal repository:

- `https://fantaking-api.dunkest.com/api/v1/leagues/1/config`
- `https://fantaking-api.dunkest.com/api/v1/schedules/{schedule_id}/matchdays/{matchday_id}`

Il codice ricava giornata e turno dal payload e applica la regola Dunkest documentata: il turno inizia un minuto prima della prima partita. In questa verifica, la richiesta di sola lettura alla configurazione ha fallito con `httpx.ConnectError: [Errno 8] nodename nor servname provided, or not known` (errore DNS). L'endpoint non è stato ritentato. Anche l'apertura diretta dell'API nel browser non è stata disponibile.

La [pagina ufficiale Dunkest sul calendario](https://www.dunkest.com/it/nba/notizie/fantabasket/18229/calendario-dunkest-nba-squadre-valide-punteggi-medi), pubblicata il 23 ottobre 2026, annuncia la Giornata 2 e rimanda al calendario nell'app, ma non fornisce fixture e orari dei singoli turni. La [guida ufficiale ai turni](https://www.dunkest.com/it/notizie/fantabasket/8774/calendario-dunkest-cosa-sono-giornata-turni) documenta la regola di avvio un minuto prima della prima partita; ciò non sostituisce l'orario specifico del turno. È prova che la giornata esiste, non prova sufficiente per identificare il prossimo turno futuro o calcolare un cutoff. Il cutoff applicabile è quindi **sconosciuto**; fixture, pool, ID e orari futuri non sono stati verificati. Non sono stati acquisiti roster/crediti, infortuni, Lineups o statistiche per un nuovo run, e non è stato invocato il comando di produzione.

## Copertura e valutazione

Nuovo pool candidato: **0**. Previsioni ibride/HGB: **0**. Record con identità verificata: **0**. Candidati riconciliabili: **0**. Manifest: **nessuno**; nessun run viene dichiarato `certified` o `uncertified` perché non è stato creato.

L'archivio GW1 resta quello diagnosticato nel precedente audit (528 candidati, 443 valori HGB, 289 record appaiati con log); era marcato non idoneo alla certificazione pre-lock e non è stato ricertificato. Non si calcolano nuove metriche.

## Test e modifiche

Nessuna modifica al codice o ai dati di forecast. Test mirati eseguiti per propagazione identità, manifest/cutoff, archiviazione e riconciliazione:

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_prediction_fixture_propagation.py \
  tests/test_role_minutes_projection.py \
  tests/test_artifact_manifest.py \
  tests/test_dunkest_cutoff_evidence.py \
  tests/test_prelock_archive.py \
  tests/test_post_match_collection.py
```

Esito: **82 passed**. La prima esecuzione ha individuato un fixture sintetico di certificazione privo dei nuovi campi obbligatori di ID e previsione shadow; è stato aggiornato soltanto il fixture di test, poi tutti i test mirati sono passati. `git diff --check` è passato. Nessun test sintetico è presentato come cattura prospettica.

## Prossimo passo

Ripetere una sola acquisizione di lettura dell'API ufficiale quando il DNS dell'ambiente risolve `fantaking-api.dunkest.com`; identificare giornata, turni e fixture reali, verificare un cutoff ancora futuro e soltanto allora procedere alla cattura prospettica.
