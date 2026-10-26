# Audit copertura ed eleggibilità forecast operativo — 2026-10-26

## Esito

Il run diagnostico `20261025T101251Z_6d20853d` non è un bundle pre-lock eleggibile e non è stato modificato. Le anomalie hanno cause distinguibili: 148 identità Dunkest mancanti derivano dall'unione di candidati Lineups senza ID con il pool statistico; 87 righe rappresentano fallback senza storico esplicitamente documentati ma il validator le rifiutava in modo indiscriminato; 2 righe sono collisioni di alias nel join normalizzato, non semplici record senza storico. La causa individuale dei 148 ID non risolti (giocatore assente dalla risposta statistica oppure alias non riconosciuto) non è dimostrabile dai file congelati.

Sono state applicate due correzioni minime e testate: lo snapshot runtime conserva la stessa riga di alias selezionata dal predictor; il validator ammette una riga senza feature solo quando tutti i campi dimostrano il fallback no-history e l'assenza della previsione shadow. La mancanza di ID ufficiali resta bloccante. Nessun ID, feature o dato storico è stato ricostruito.

## Stato Git e preservazione

All'inizio la working tree conteneva già modifiche e file non tracciati relativi a pipeline, report, test, configurazione locale e artefatti Graphify. Sono stati preservati. Per questo intervento risultano modificati soltanto:

- `src/dunkest/models/predictor.py`
- `scripts/archive_dunkest_pre_lock_run_v1.py`
- `tests/test_role_minutes_projection.py`
- `tests/test_prelock_archive.py`
- questo nuovo report

Nessun archivio, forecast, report precedente, rose o file di configurazione è stato sovrascritto. Non sono stati eseguiti scraping, training, forecast, commit o push.

## Evidenze sul run

Artefatti letti in `data/predictions/20261025T101251Z_6d20853d/` e snapshot associati:

| Evidenza | Riscontro | Interpretazione |
|---|---:|---|
| Universo `player_forecast_snapshot` | 519 righe | Candidati conservati nel run. |
| `dunkest_player_id` nullo | 148 | I 148 record trovano corrispondenza per `player_key` in `current_lineups_market.csv`; quel CSV non contiene ID Dunkest. Il percorso live aggiunge candidati Lineups non abbinati al pool statistiche e non può assegnare loro l'ID. È dimostrato il percorso che produce i null; senza la risposta grezza del listino/statistiche non è possibile distinguere assenza dalla fonte e mancata corrispondenza del nome per ciascun giocatore. |
| Runtime feature status | 430 matched, 87 missing, 2 ambiguous | I conteggi coincidono con il manifest incompleto. |
| 87 righe `missing` | candidate key count 1; source feature rows 0; `history_source=history_feature_row_missing`; shadow minuti assente | Fallback operativo esplicito, non perdita casuale del writer. Il vecchio controllo di eleggibilità trattava tuttavia ogni `missing` come errore, anche in questo caso senza storico e senza shadow. |
| 2 righe ambigue | Bobby Portis e Terrence Shannon Jr.; 1 chiave normalizzata, 2 righe sorgente ciascuno | Alias distinti nei log storici collassano allo stesso `player_key`. `build_feature_matrix` conserva entrambe le forme testuali; la lookup operativa sceglie deterministicamente l'ultima riga normalizzata. Lo snapshot runtime non applicava la stessa selezione e quindi perdeva l'identità univoca del join. |
| Identificatori sorgente delle collisioni | Bobby Portis / Bobby Portis Jr. (stesso NBA Player ID); Terrence Shannon Jr. / Terrence Shannon Jr (stesso NBA Player ID) | Conferma che si tratta di alias duplicati, ma non certifica da sola quale alias debba essere canonico nel dato Dunkest. Non è stata fatta alcuna fusione retroattiva dei dati. |
| Manifest del run | `archive_status=incomplete`, `snapshot_set_complete=false`, identità stabile falsa, runtime incompleto | Il run è correttamente non eleggibile. Forecast timestamp `2026-10-25T10:12:14Z`, cutoff `2026-10-25T20:59:00Z`; hash/versioni presenti. |
| `archive_manifest.json` | Assente nel run diagnostico | Nessun sigillo o registrazione immutabile del run. |
| Outcome ufficiali riconciliati per GW3 | Nessun archivio `post_match_*` trovato per questo run | Non valutabile e non riconciliabile al momento. |

Le 87 righe non vanno confuse con i due alias ambigui: la prima categoria non ha alcuna riga sorgente e dichiara il fallback; la seconda ha più righe sorgente per la stessa chiave e richiedeva la stessa regola deterministica già usata dall'inferenza.

## Ciclo `archive_manifest.json` ed eleggibilità

Il percorso `scripts/archive_dunkest_pre_lock_run_v1.py::archive_run` non considera la mera presenza dei file sufficiente. Carica e controlla il manifest del run, requisiti e freschezza degli snapshot, identità dei candidati, validazione del bundle versionato, fixture/mapping e certificazione pre-lock. Calcola l'eleggibilità come congiunzione dei controlli; prepara una copia temporanea, calcola l'inventario/hash, scrive `archive_manifest.json`, quindi pubblica l'archivio e la registrazione nel registry in modo atomico. Un bundle diagnostico può quindi essere sigillato con `pre_lock_eligible=false`; il sigillo di integrità non equivale all'eleggibilità. Il reviewer verifica hash e registry, e il gate postpartita rifiuta gli archivi incompleti anche in modalità diagnostica.

I test esistenti coprono archivio con manifest/hash/registry, bundle incompleto, reviewer che non promuove archivi incompleti e gate postpartita fail-closed. È stato aggiunto anche un test che crea un archivio con file presenti ma ID Dunkest nullo e verifica che il sigillo conservi `pre_lock_eligible=false`. Non è stata eseguita l'archiviazione del run reale per evitare di creare o alterare artefatti.

## Correzioni applicate

1. **Snapshot runtime coerente con il predictor.** `predict_players` già deduplicava la lookup per `_key` con `keep="last"`; il nuovo helper `_selected_runtime_feature_rows` applica la medesima selezione, mantenendo allineata la matrice HGB. Il PDK e la previsione minuti non cambiano: cambia solo la riga di provenienza salvata per il join successivo. Test con alias Bobby Portis verifica scelta e allineamento della matrice.
2. **Fallback no-history esplicito accettato, fallback non documentato respinto.** Il validator consente `feature_match_status=missing` soltanto se: chiave candidata unica, zero righe sorgente, shadow status unavailable, `history_source=history_feature_row_missing` e minuti shadow nulli. Se una qualsiasi condizione manca, il bundle resta incompleto. Questo rimuove un falso blocco sui fallback previsti senza rilassare i requisiti per mismatch reali.
3. **Guard rail sugli ID verificato.** Test con tutti i file presenti ma `dunkest_player_id` nullo conferma che l'archivio diagnostico resta `pre_lock_eligible=false`.

Non è stata introdotta una ricostruzione degli ID né una scelta automatica tra alias di fonti diverse.

## Criteri oggettivi di eleggibilità

Un run futuro può essere considerato eleggibile solo se:

1. ogni candidato valutato ha un ID Dunkest stabile e univoco, oppure è escluso dal contratto con motivo esplicito e senza essere contato come forecast valutabile;
2. gli ID forecast, giocatore e partita sono univoci e i riferimenti tra snapshot coerenti;
3. ogni riga runtime è `matched`, oppure soddisfa integralmente il caso no-history/shadow-unavailable verificabile sopra; nessuna riga `ambiguous` è ammessa;
4. forecast, cutoff, fixture, stagione/giornata, modello, configurazione, provenienza e timestamp sono coerenti e pre-lock; hash e schema passano il reviewer;
5. tutti gli snapshot obbligatori, inclusi coach e shadow secondo il contratto, sono presenti o marcati in modo esplicito secondo le regole del contratto; un file presente ma invalido non vale come completo;
6. il reviewer produce esito valido e l'`archive_manifest.json` registra `pre_lock_eligible=true` con registry/hash verificati;
7. solo dopo la partita, outcome ufficiali vengono acquisiti separatamente e riconciliati con chiavi stabili di partita/giocatore, squadre e data. Ambiguità, outcome nulli o partite mancanti restano esclusi, mai convertiti a zero.

Il run GW3 resta non eleggibile anche dopo queste correzioni: i 148 ID nulli e le 2 righe ambigue non vengono sanati retroattivamente e i suoi snapshot persistiti non sono stati riscritti. La raccolta prospettica non è dichiarata completata.

## Test e controlli eseguiti

- `./.venv/bin/pytest -q tests/test_prelock_archive.py tests/test_role_minutes_projection.py tests/test_artifact_manifest.py tests/test_post_match_collection.py` — **103 passed**, 1 warning ambientale `joblib` sul conteggio dei core fisici (fallback al conteggio logico).
- `./.venv/bin/python -m py_compile src/dunkest/models/predictor.py scripts/archive_dunkest_pre_lock_run_v1.py tests/test_role_minutes_projection.py tests/test_prelock_archive.py` — completato senza errori.
- `git diff --check` — completato senza errori.
- Ispezione in sola lettura di manifest/Parquet del run e dei moduli di mapping, predictor, writer, archiviatore, reviewer e gate outcome. Nessuna nuova acquisizione dati eseguita.

## Limiti residui

- La risposta grezza del listino/statistiche che avrebbe dovuto assegnare gli ID non è contenuta nel bundle; causa specifica per ciascuno dei 148 candidati non determinabile senza un nuovo run naturale o snapshot grezzo già disponibile.
- Il mapping per `player_key` risolve i due alias al livello del predictor, ma non certifica l'identità Dunkest ufficiale. L'eligibilità continua a richiedere tale ID.
- Il manifest riporta `availability_observed_at_utc` nullo benché siano presenti timestamp specifici di Lineups/infortuni. È un difetto di aggregazione dei metadati, ma non è stato alterato nell'ambito di questo audit perché non ha creato le tre anomalie richieste; va verificato prima di affidarsi a quel campo aggregato come prova temporale.
- Non sono presenti outcome ufficiali riconciliati per GW3; nessuna metrica predittiva o validazione OOS è stata prodotta.
- Il sigillo certifica l'integrità della copia al momento dell'archiviazione; il run diagnostico non ha un sigillo pre-lock originario. La sua assenza è un motivo sufficiente per non trattarlo come bundle prospettico certificato.
