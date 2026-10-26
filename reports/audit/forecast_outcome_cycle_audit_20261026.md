# Audit end-to-end del ciclo forecast e outcome — 2026-10-26

## Esito

È stato verificato un difetto concreto nel flusso ordinario: `dunkest run` salvava gli artefatti del forecast, ma terminava senza chiamare l'archiviatore pre-lock e il reviewer. L'archiviazione era disponibile soltanto attraverso un comando separato, e lo script `run_and_archive_prelock_v1.sh` era specifico del workflow di apertura stagione. Questo spiega perché un run ordinario poteva non avere `archive_manifest.json`, anche se i suoi artefatti erano stati salvati.

Ho aggiunto al termine del run ordinario un tentativo di archiviazione seguito dalla revisione indipendente. I controlli d'eleggibilità non sono stati rilassati: un run incompleto può essere sigillato solo come diagnostico (`pre_lock_eligible=false`), e l'output distingue esplicitamente tale stato da un bundle verificato. Errori dell'archiviatore o del reviewer vengono mostrati come errore e non come forecast valido.

Non ho eseguito un forecast reale né modificato archivi esistenti. Non esistono in questa verifica un nuovo run naturale eleggibile o outcome ufficiali riconciliati; il ciclo non è dichiarato completato e non sono state calcolate metriche.

## Flusso verificato

| Fase | File/funzione | Input e output | Gate e blocchi |
|---|---|---|---|
| Forecast operativo | `src/dunkest/__main__.py::main`, `run_train`, `run_predict`, `run_optimize` | Dati raccolti/cache, fixture e rosa → previsioni giocatori/coach e soluzioni | Fixture mapping verificato prima del training; l'ottimizzatore rimuove `expected_min_model_shadow` dal proprio input operativo in `src/dunkest/pipeline/optimize.py::run_optimize`. |
| Persistenza del run | `src/dunkest/report/artifacts.py::save_run_artifacts` | Predizioni, soluzioni, modelli e coach → directory append-only sotto `data/predictions/<run_id>` con manifest, pre-match snapshot e snapshot versionati di giocatori, runtime, shadow e coach | Errori di persistenza e snapshot incompleti sono registrati; `expected_min` e `expected_min_model_shadow` sono salvati distintamente quando disponibili. Il forecast non include outcome come input. |
| Sigillo pre-lock | `scripts/archive_dunkest_pre_lock_run_v1.py::archive_run` | Directory run → copia immutabile sotto `data/archives/pre_lock/season_id=.../gw=.../<run_id>`, `archive_manifest.json` e registry | Richiede artefatti base, snapshot richiesti, freschezza, contenuto, fixture verificata, identità e bundle versionato. I controlli congiunti determinano `pre_lock_eligible`; la sola presenza dei file non basta. La mancanza non esplicitamente ammessa di snapshot richiesti interrompe l'archiviazione. |
| Revisione indipendente | `scripts/review_dunkest_pre_lock_archive_v1.py::review` | Archivio sigillato → stato e motivi di revisione | Ricontrolla inventario/hash, registry, freschezza, contenuto, snapshot, fixture ed eleggibilità. Il reviewer non promuove un archivio incompleto. |
| Acquisizione postpartita | `scripts/build_dunkest_post_match_results_v1.py::main` | Archivio eleggibile, snapshot fixture/market congelati, risultati ufficiali Dunkest e log NBA → audit di copertura e archivio post-match separato | Attende il cutoff sicuro dopo le partite. La corrispondenza usa giocatore/market, squadra, avversario, data e fixture con un solo candidato; ambiguità e outcome mancanti restano unresolved/missing, non zero. Le fonti ufficiali devono essere presenti nella cache locale o esplicitate tramite opzioni. |
| Persistenza outcome | `src/dunkest/report/artifacts.py::save_post_match_snapshot` | Risultati giocatori/coach e provenienza → `data/archive/<season>/gw<gw>/post_match_*`, manifest/hash e registry | Scrittura immutabile e idempotenza tramite chiave; gli outcome non riscrivono il forecast originario. |
| Valutazione | `scripts/run_dunkest_postmatch_oos_pipeline_v1.py::validate_archive`, `run_pipeline`; `scripts/evaluate_archived_run_post_match_v1.py` | Bundle pre-lock e archivio outcome → report di copertura/metriche | Rifiuta archivi non eleggibili nella modalità ordinaria; l'opzione diagnostica non certifica OOS. Un collector incompleto non produce una valutazione completa. |

## Prossimo blocco concreto

### Risolto in questa modifica

- **Mancata propagazione automatica al sigillo/reviewer:** il normale entry point non chiamava nessuno dei due. Ora, dopo `save_run_artifacts`, `src/dunkest/__main__.py::_archive_and_review_run` invoca entrambi in sequenza e stampa esito e percorso. Non interviene prima della generazione delle rose e non cambia i dati passati al solver.

### Ancora bloccante o in attesa

- **ID Dunkest mancanti:** per il run diagnostico citato dai report, 148 candidati non avevano ID ufficiale. Il percorso noto li conserva nel pool, ma i dati congelati non permettono di attribuire per ciascuno assenza dalla fonte o mancata corrispondenza del nome. Non viene assegnato un ID per similarità; il gate resta bloccante.
- **Mapping ambiguo:** le correzioni già presenti nel working tree allineano la selezione degli alias tra predictor e snapshot runtime. Le due righe ambigue del vecchio run non sono ricostruite né riscritte retroattivamente.
- **Feature mancanti:** il validator ammette esclusivamente il fallback no-history esplicito e privo di shadow già documentato nelle modifiche preesistenti. Altri candidati runtime mancanti o ambigui continuano a rendere il bundle incompleto.
- **Listino/snapshot obbligatori:** la mancanza del listino è rappresentata esplicitamente come requisito mancante e rende il run non eleggibile. Gli altri snapshot obbligatori assenti o non verificabili continuano a impedire il sigillo oppure l'eleggibilità, secondo il gate corrente.
- **Outcome ufficiali:** l'acquisizione e la valutazione sono passaggi postpartita separati e attualmente manuali. Non risultano outcome formali riconciliati per il run GW3 diagnostico. Nessun dato postpartita è stato acquisito in questo audit.
- **Dati sorgente non ancora osservati:** non è possibile sapere staticamente se un futuro run naturale avrà ID stabili, copertura completa, cutoff verificato e outcome ufficiali univoci. L'integrazione dell'archiviazione non risolve queste lacune di fonte.

## Confronto minuti: dati già conservati e condizioni

Il writer salva `expected_min`, `expected_min_model_shadow` e le componenti PDK presenti, in record separati/versionati. Il bundle archiviato comprende snapshot giocatore, runtime feature, shadow e coach; il reviewer ne verifica schema, riferimenti e hash. L'ottimizzatore continua a escludere il campo shadow.

Il collector postpartita usa i log giocatore NBA per i minuti e i risultati ufficiali Dunkest per il PDK, collegandoli alla fixture congelata. DNP/zero non sono da inferire da una riga mancante: il collector o la fonte devono fornire evidenza verificabile; altrimenti la riga resta non riconciliata. Per il replay PDK servono un bundle eleggibile, outcome ufficiale univoco e componenti sufficienti; `recalculate_pdk_projection` consente l'override dei minuti, ma la correzione DvP e i vincoli minuti devono essere mantenuti identici tra rami e applicati una sola volta. Non ho eseguito il replay perché i prerequisiti prospettici non sono soddisfatti.

## Modifiche di questa operazione

- `src/dunkest/__main__.py`: aggiunto il tentativo automatico di archivio e reviewer dopo la persistenza ordinaria, con esiti separati per errore, archivio diagnostico e verifica pre-lock positiva.
- `tests/test_run_archive_integration.py`: test offline che garantiscono la conservazione dello stato non eleggibile e la segnalazione del fallimento senza proseguire al reviewer.
- Questo report.

Le modifiche preesistenti in `src/dunkest/__main__.py` e negli altri file della working tree sono state mantenute. Nessun archivio o forecast è stato aperto in scrittura.

## Test eseguiti

- `./.venv/bin/pytest -q tests/test_run_archive_integration.py tests/test_prelock_archive.py tests/test_post_match_collection.py tests/test_artifact_manifest.py` — **82 passed**.
- `./.venv/bin/python -m py_compile src/dunkest/__main__.py tests/test_run_archive_integration.py` — completato senza errori.
- `git diff --check` — completato senza errori.

Non è stata eseguita l'intera suite, né un forecast, scraping o training.

## Passi operativi futuri

1. Eseguire un normale forecast dopo che le fonti necessarie sono disponibili; il comando `dunkest run` ora archivia e revisiona automaticamente il run appena salvato. Verificare che il report indichi `Bundle pre-lock verificato`; se indica archivio diagnostico o errore, non procedere come se fosse eleggibile.
2. Dopo il completamento delle fixture, eseguire `./.venv/bin/python scripts/run_dunkest_postmatch_oos_pipeline_v1.py --archive-dir <percorso-bundle-pre-lock> --data-dir <data-dir> --output-dir <nuovo-percorso-report>` senza `--allow-ineligible-diagnostic`. Il collector attende il cutoff sicuro, controlla le fonti ufficiali disponibili e salva outcome separati. Un risultato non pronto o parziale non è una validazione completa.
3. Solo quando esistono archivio pre-lock eleggibile, outcome ufficiali riconciliati e copertura adeguata, eseguire il valutatore/replay minuti con join univoci e gli stessi cutoff.

## Stato finale

Il ciclo standard ora prova automaticamente il passaggio di archiviazione e revisione; resta necessario un run naturale per verificarlo con dati reali. Mancanza di ID/mapping, esito reviewer negativo, fonti postpartita assenti o riconciliazione incompleta continuano a bloccare correttamente la valutazione. Il ciclo end-to-end prospettico non è certificato e nessun miglioramento predittivo è stato misurato.
