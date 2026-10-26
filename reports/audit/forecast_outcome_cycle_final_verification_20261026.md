# Verifica finale del ciclo operativo forecast–outcome — 2026-10-26

## Esito

Ho verificato il precedente report e il percorso aggiunto al comando ordinario. È emerso un difetto riproducibile: se l'archiviatore o il reviewer falliva, il CLI stampava un avviso ma poteva terminare con codice 0. Ora un errore tecnico viene mostrato e causa `SystemExit(2)` **dopo** il salvataggio del forecast. Un archivio diagnostico revisionato ma non eleggibile resta invece un esito distinto: non viene promosso, ma non trasforma un forecast riuscito in errore tecnico.

Il comportamento su un run reale resta non verificato. Nessun forecast, scraping, training, outcome o archivio storico è stato generato o modificato. La pipeline prospettica non è certificata.

## Percorso verificato

`src/dunkest/__main__.py::main` esegue previsione e ottimizzazione, chiama `save_run_artifacts`, quindi `_archive_and_review_run`; infine `_report_archive_review` presenta l'esito.

| Esito | Messaggio/comportamento | Exit code |
|---|---|---:|
| Archivio e reviewer attestano entrambi l'eleggibilità | “Bundle pre-lock verificato” | 0 |
| Archivio sigillato ma uno o più gate non superati | “Bundle archiviato a fini diagnostici, non eleggibile”, con stato e percorso | 0 |
| Errore tecnico di archivio o revisione, risposta invalida o processo non avviabile | Avviso esplicito; gli artefatti del forecast già salvati restano disponibili | 2 |

L'archiviatore copia il run in una nuova directory e il reviewer opera in sola lettura: questa chiamata non riscrive il forecast sorgente. I gate non sono cambiati in questa operazione. Il reviewer rivaluta hash/registry, freschezza, contenuto, fixture e snapshot; l'esistenza dei file non basta. L'ID Dunkest stabile resta richiesto dal validatore: il test esistente con ID nullo continua a produrre `pre_lock_eligible=false`.

## Minuti e outcome

Il writer `src/dunkest/report/artifacts.py::save_run_artifacts` conserva `expected_min` e `expected_min_model_shadow` come valori distinti. `pipeline/optimize.py::run_optimize` esclude il campo shadow dall'input operativo del solver.

Il processo postpartita separato verifica prima il bundle pre-lock, aspetta il cutoff sicuro, usa la fixture congelata e collega gli outcome ufficiali Dunkest e i log NBA. La costruzione degli actuals usa giocatore normalizzato, squadra/avversario, data e fixture, e accetta soltanto una fixture candidata; assegnazioni squadra conflittuali e PDK discordanti causano errore, mentre righe non univoche o mancanti restano non riconciliate. I risultati vengono salvati da `save_post_match_snapshot` in un archivio separato e immutabile, senza riscrivere lo snapshot pre-lock.

La riconciliazione delle fonti usa un join composito e controlli di unicità; non è un join universale tramite ID Dunkest nell'outcome ufficiale. Candidati privi di identità stabile non possono comunque superare il gate pre-lock. Nessun replay minuti/PDK è stato eseguito.

## Correzione e file

- [src/dunkest/__main__.py](/Users/simone/Documents/Dunkest/src/dunkest/__main__.py): un errore tecnico di archiviazione/revisione ora termina con codice 2; il caso diagnostico incompleto resta distinto.
- [tests/test_run_archive_integration.py](/Users/simone/Documents/Dunkest/tests/test_run_archive_integration.py): verifica sequenza di chiamata, mancata promozione di bundle incompleti, messaggi distinti e codice non-zero in caso di errore tecnico.
- Questo report.

Le modifiche locali preesistenti sono state mantenute.

## Test e controlli

- `./.venv/bin/pytest -q tests/test_run_archive_integration.py tests/test_prelock_archive.py tests/test_post_match_collection.py tests/test_artifact_manifest.py tests/test_cli_roster_budget.py tests/test_next_gameweek_workflow.py` — **95 passed**.
- `./.venv/bin/python -m py_compile src/dunkest/__main__.py scripts/archive_dunkest_pre_lock_run_v1.py scripts/review_dunkest_pre_lock_archive_v1.py scripts/build_dunkest_post_match_results_v1.py scripts/run_dunkest_postmatch_oos_pipeline_v1.py tests/test_run_archive_integration.py` — completato senza errori.
- `git diff --check` — completato senza errori.

Non è stata eseguita l'intera suite, né il comando ordinario su dati reali.

## Limiti residui

- Gli ID Dunkest mancanti documentati restano bloccanti; non sono stati inferiti da nomi simili.
- Nessun nuovo run naturale eleggibile o outcome ufficiale riconciliato è stato verificato.
- I test attestano il comportamento software su fixture offline, non l'accessibilità o copertura futura delle fonti esterne.
- La pipeline prospettica potrà dirsi verificata soltanto dopo un run naturale con reviewer positivo e successivo archivio di outcome ufficiali riconciliati, con copertura e join univoci.
