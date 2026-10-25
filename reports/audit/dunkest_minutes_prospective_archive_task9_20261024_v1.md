# Task 9 — Archivio prospettico dei minuti

**Data audit:** 2026-10-24  
**Stato:** infrastruttura aggiornata; nessuna nuova giornata certificata o valutata.

## Componenti riutilizzati

- `pipeline.predict` costruisce il pool `candidate_forecasts` dal forecast grezzo, prima del filtro `eligible`; conserva quindi anche gli OUT e gli altri candidati esclusi dall'optimizer. Aggiunge turno, fixture NBA/Dunkest e timestamp osservati di Lineups/infortuni.
- `models.predictor.predict_players` produce i minuti operativi ibridi (`expected_min`) e la previsione HGB shadow (`expected_min_model_shadow`, nullable). Il mercato Dunkest (`dunkest_players_...`) espone già un ID `id`, ma il costruttore della riga di previsione non lo riportava.
- `report.artifacts.save_run_artifacts` salva `player_forecast_snapshot.parquet`, gli input pre-match, i loro hash e il manifest; il bundle di run è immutabile una volta archiviato.
- `archive_dunkest_pre_lock_run_v1.py` e `review_dunkest_pre_lock_archive_v1.py` verificano cutoff e integrità prima della certificazione/archiviazione.
- `build_dunkest_post_match_results_v1.py` produce una riga per candidato e conserva gli stati `appeared`, `zero_minutes_verified`, `dnp_documented`, `outcome_missing`, `outcome_ambiguous`, `fixture_unverified` e `official_pdk_only`. Un'assenza dai log non viene convertita in zero. PDK ufficiale e proxy NBA restano distinti. L'archivio post-partita usa hash e chiave idempotente.
- `run_dunkest_postmatch_oos_pipeline_v1.py` collega raccolta e valutazione. `dunkest.evaluation.minutes_comparison` fornisce metriche appaiate e bootstrap per partita; lo script Task 8 rimane una riproduzione diagnostica del singolo GW1, non è una certificazione cumulativa.

## Causa e correzione

Il mercato conserva l'identificativo stabile Dunkest `id`, ma `predict_players` costruiva una nuova riga di output copiando solo nome, squadra, ruolo e previsioni: l'ID veniva perso in quel passaggio. Di conseguenza il salvataggio ripiegava su `normalized_player_key`, mentre il collegamento post-partita dipendeva dalla corrispondenza di nome/squadra/partita.

La correzione minima propaga ora `dunkest_player_id` dal record di mercato. Al salvataggio ogni candidato riceve `forecast_run_id`, `forecast_record_id` deterministico, stato esplicito per disponibilità della previsione ibrida e shadow, e conserva il valore shadow nullo quando assente. Una mancata previsione non viene sostituita o imputata. La certificazione pre-lock e la verifica dell'archiviatore ora richiedono l'ID Dunkest presente e univoco per giocatore/partita; i run storici privi di tale campo non diventano certificabili retroattivamente.

I record post-partita esistenti mantengono separate le informazioni pre-lock (`status`, ruolo e squadra congelati) e l'esito successivo (`outcome_status`, fonti e classificazione). La chiave di riconciliazione NBA continua a richiedere mapping verificato e corrispondenza giocatore-squadra-`nba_game_id`; in caso di più righe o collegamenti non verificati il risultato è ambiguo/non verificato, non scelto arbitrariamente.

## Copertura verificata e lacune

L'archivio diagnostico GW1 del 2026-27 documentato nell'audit Task 8 contiene 528 candidati, 528 minuti ibridi, 443 valori HGB shadow, 295 candidati con log NBA collegato e 289 record appaiati valutabili. I 233 candidati senza log non sono etichettati come zero. Il run è esplicitamente `pre_lock_eligible=false`; non è una giornata certificata e non è stato modificato.

La copertura di esiti ufficiali Dunkest resta limitata secondo l'audit precedente; i log NBA non coprono necessariamente DNP e giocatori senza apparizione. Non risultano più forecast origin certificati con cui calcolare una valutazione walk-forward cumulativa affidabile. Perciò copertura archivio storica e copertura metrica rimangono concetti distinti e non si dichiara beneficio comparativo.

Prerequisiti per la valutazione futura: acquisire realmente il forecast prima del cutoff verificato; includere nel manifest l'intero pool e gli input congelati con provenienza; mantenere gli ID stabili e fixture univoche; raccogliere roster/log o altra evidenza sufficiente per attribuire zero/DNP; accumulare più origin temporali certificati. Il confronto deve poi usare la stessa intersezione di record con minuti ibridi, HGB e minuti effettivi validi, riportando numerosità e copertura, metriche per giornata/fold e bootstrap raggruppato per partita.

## Test

Test pertinenti: propagazione ID al predictor e allo snapshot; stato esplicito quando HGB manca; ID record e run; fixture multi-turno; validazione di cutoff/manifest; riconciliazione missing/zero/DNP e idempotenza; appaiamento e metriche. Comando eseguito:

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_prediction_fixture_propagation.py \
  tests/test_role_minutes_projection.py \
  tests/test_artifact_manifest.py \
  tests/test_prelock_archive.py \
  tests/test_post_match_collection.py \
  tests/test_minutes_comparison.py
```

Esito: **82 passed**. Il primo invio senza `PYTHONPATH=src` non aveva raccolto i test (`ModuleNotFoundError: dunkest`); il comando corretto sopra è passato. La suite completa non è stata eseguita perché il cambiamento è limitato al percorso archivio/predictor e ai test mirati.

## Limiti e decisione

Non è stata eseguita una cattura live, una certificazione reale, né una ricostruzione retroattiva. Gli snapshot storici non acquistano ID o evidenze mancanti. L'audit Task 8 rimane diagnostico e selezionato sui giocatori con log; la valutazione cumulativa è **insufficiente** fino ad almeno più origin certificati con esiti completi.

**Prossimo obiettivo unico:** acquisire il primo forecast prospettico dopo aver verificato che la fixture, il cutoff e tutti gli input obbligatori siano disponibili prima del lock; quindi riconciliare tutti i candidati con evidenza di roster sufficiente a classificare gli zero minuti.
