# Dunkest 2.0 — preparazione confronto minuti operativi e HGB shadow

**Data:** 2026-10-26
**Esito:** procedura definita; esperimento non eseguito, perché i bundle locali non superano i criteri correnti e non ci sono outcome post-match ufficiali riconciliati. Nessuna modifica al codice, ai modelli o agli archivi.

## 1. Implementazione verificata

### Minuti operativi `expected_min`

In `src/dunkest/models/predictor.py::predict_players`, `_base_minutes` costruisce la richiesta iniziale dai log storici (`e_min_5` e `e_min_season`: 65%/35% quando entrambi esistono). La confidenza del campione `n_games/(n_games+12)` regola quanto lo storico pesa rispetto al prior attuale.

- Se esiste una designazione Lineups `QUINTETTO` o `PANCHINA`, `_lineup_minutes_prior` combina ruolo indicato e CR. Il prior viene fuso con lo storico con un peso storico limitato (0,35 × confidenza) quando il ruolo corrente è noto.
- Senza storico, il prior usa lineup e CR; se manca anche la designazione usa la curva CR→minuti; se manca pure CR, il fallback è 1 minuto.
- I minuti sono limitati da ruolo/CR. `_apply_current_role_competition` applica i cap in base alla profondità del roster e alla designazione; `allocate_positional_minutes` ridimensiona i minuti richiesti entro la capacità posizionale e pone a zero i giocatori con `p_play=0`.
- Disponibilità/infortuni regolano `p_play` e il PDK atteso. Non costituiscono una misura continua dei minuti condizionati alla presenza.

`expected_min` è quindi un output operativo di regole, prior, storico e vincoli di roster, non una previsione HGB. Cambiamenti lineup/CR/roster possono modificare i minuti anche senza una feature di trend che li identifichi causalmente.

### Minuti HGB shadow `expected_min_model_shadow`

`train_models` addestra un `HistGradientBoostingRegressor` sul target storico `target_min` se ci sono almeno 200 target minuti finiti. Usa la stessa matrice numerica delle feature del predictor PDK e parametri fissati nel codice (180 iterazioni, learning rate 0,06, max leaf 31, L2 5, min leaf 40, random state settings). In inferenza applica la matrice/mediane del fit e limita la predizione a 0–48 minuti. È il valore grezzo di shadow: non passa dai cap lineup/roster, dalla concorrenza o dall’allocazione dei minuti operativi.

`predict_players` salva l’output come `expected_min_model_shadow`, ma il PDK operativo viene costruito con `expected_min`. `pipeline/optimize.py::run_optimize` rimuove esplicitamente `expected_min_model_shadow` prima di chiamare il solver. Lo shadow non alimenta le rose.

### PDK operativo e controfattuale

Il PDK iniziale viene composto da `recalculate_pdk_projection` in `src/dunkest/models/predictor.py`. Con il valore atteso dei minuti calcola:

- componente minuti: `expected_min × pdk_rate_for_projection`;
- componenti ensemble e prior scalate rispetto a `implied_min`;
- componente RF storico scalata, se ha peso non nullo;
- blend con pesi di proiezione e confidenza storico `n_games/(n_games+12)`;
- PDK condizionale e PDK atteso moltiplicato per `p_play`.

La funzione condivisa accetta `expected_minutes=` come override. Un replay isolato può quindi chiamare la funzione una volta con `expected_min` e una volta con il candidato HGB, lasciando invariati rate, ensemble/prior, pesi, storico, `p_play` e gli altri componenti.

Ci sono due precisazioni operative:

1. il valore HGB grezzo non ha subito i cap e l’allocazione posizionale. Per un confronto **minuti previsionali** va misurato sia grezzo (estimand HGB) sia dopo un post-processing dichiarato e identico ai vincoli applicati al candidato operativo. Per il confronto **PDK** l’override deve rispettare i vincoli del forecast; applicare `expected_min_model_shadow` senza cap/allocazione introdurrebbe una variante di minuti diversa da quella utilizzabile in produzione;
2. `pipeline/predict.py` applica successivamente la correzione DvP al PDK. Il replay deve riapplicare lo stesso fattore/correzione archiviato una sola volta, o lasciare DvP fuori da entrambi i bracci e definire il target come PDK base. Non si deve riutilizzare un PDK già corretto e moltiplicarlo nuovamente. Il writer porta i campi DvP nei forecast quando prodotti, ma `PDK_REPLAY_REQUIRED_COLUMNS` non li rende obbligatori: prima del replay va verificata la presenza per ogni record di base/frazione/status e riferimento/hash dello snapshot; se mancano, valutare solo il PDK base oppure escludere il confronto PDK finale.

`recalculate_pdk_projection` è sufficiente per ricomporre i componenti PDK descritti, ma non applica i vincoli minuti; il protocollo deve quindi separare chiaramente replay composizionale e allocazione operativa.

## 2. Fonti degli outcome e identificazione

- **Minuti NBA:** i log giocatore NBA contengono `PLAYER_ID`, `GAME_ID`, `GAME_DATE` e `MIN`; il join affidabile è per ID giocatore NBA + ID partita, non per solo nome/data. La cache corrente non è di per sé una raccolta prospettica di forecast-outcome; l’acquisizione outcome va registrata dopo il lock, con timestamp e provenienza separati.
- **PDK ufficiale:** `src/dunkest/data/dunkest/client.py::fetch_dunkest_round_players` interroga la tabella ufficiale per stagione, giornata e round e salva risultati per round. Il collegamento al forecast richiede mapping verificato tra `nba_game_id`, fixture/turno Dunkest e ID giocatore Dunkest. Non equiparare un aggregato di gameweek a un PDK di singola partita.
- `src/dunkest/report/artifacts.py::save_post_match_snapshot` conserva esiti separati e immutabili; `src/dunkest/data/dunkest/fixtures.py::load_post_match_results_archive` richiede manifest, hash, source e controllo di timing/copertura. Il loader richiede esiti con `nba_game_id` e PDK effettivo, ma l’archivio locale attuale non contiene record post-match formali per GW1–GW3.

**DNP e zero minuti:** una riga mancante nel log non è zero. Classificare minuti positivi solo con outcome ufficiale riconciliato. Usare zero soltanto quando una fonte ufficiale conferma esplicitamente zero minuti/DNP. DNP verificato, zero minuti verificato, outcome non ancora disponibile, mapping ambiguo e record non riconciliabile devono essere categorie separate. Se lo stato DNP non è disponibile nella fonte ufficiale acquisita, il record è non valutabile per la metrica minuti, non zero imputato. Per il PDK, usare esclusivamente l’outcome PDK ufficiale riconciliato; un outcome nullo non equivale a 0 PDK.

## 3. Eleggibilità e disponibilità attuale

L’archivio pre-lock versionato richiede bundle certificato e hash validi, cutoff verificato, forecast individuale con ID stabili, riferimenti partita/turno verificati, feature runtime coerenti e shadow snapshot separato. Il reviewer valida schema, unicità, coerenza ID, timestamp e hash. I file presenti non bastano a dichiarare eleggibilità.

Inventario locale eseguito in sola lettura:

- 5 `archive_manifest.json`, tutti GW1 2026/27;
- 4 sono `pre_lock_eligible=false`, `incomplete_evidence`;
- 1 (`20261018T124836Z_e475d5d9`) dichiara `pre_lock_eligible=true` nello schema archivio **v1 legacy**. Il validatore corrente classifica i forecast legacy come `legacy` perché non hanno il contratto di snapshot versionato; quindi non è eleggibile secondo i criteri correnti;
- nessun archivio formale `data/archive/<season>/gw*/post_match_*` con manifest/outcome è presente;
- il run GW3 `20261025T101251Z_6d20853d` è diagnostico/non eleggibile e non è ammesso come prova prospettica.

**Conclusione dati:** zero bundle attualmente eleggibili con outcome riconciliati per entrambi gli esperimenti. Non calcolo metriche e non inizio replay.

## 4. Protocollo futuro

### Gate di ingresso

Per ciascun run naturale: revisione positiva con `pre_lock_eligible=true` secondo schema corrente; forecast pre-lock e cutoff antecedenti al primo lock pertinente; stessi `forecast_record_id`, ID Dunkest, ID NBA e ID partita/turno senza duplicati o ambiguità; minuti operativi e shadow disponibili secondo status; snapshot/hash e componenti PDK completi; archivio outcome acquisito dopo le partite, verificato e collegato al medesimo game/turn. Bundle legacy, GW3 e diagnostici sono esclusi prima delle metriche.

### A — accuratezza minuti

Campione primario: tutte le osservazioni appaiate con forecast operativo e shadow disponibili e outcome minuti verificato per la stessa partita. Riportare n/coverage e stato esclusioni per ogni motivo. Calcolare per `expected_min` e `expected_min_model_shadow` MAE, RMSE e bias (`previsione − minuti effettivi`), sia per shadow grezzo sia, come analisi operativa secondaria, dopo la stessa post-elaborazione di ruolo/cap/allocazione. Separare DNP/zero verificati e partite con minuti positivi; non escludere selettivamente errori elevati. Per i DNP, trattare zero come minuto effettivo solo con evidenza esplicita e riportare anche le metriche condizionate a minuti positivi come analisi distinta, non sostitutiva.

### B — effetto PDK dei minuti

Per ogni identico `forecast_record_id` e medesimi componenti:

1. ricalcolare PDK con i minuti operativi archiviati;
2. applicare l’override HGB shadow, con medesime regole di clamp/competizione/allocazione predefinite prima di osservare gli outcome;
3. richiamare la funzione condivisa `recalculate_pdk_projection` preservando `pdk_rate_for_projection`, ensemble/prior, `implied_min`, `has_history`, `n_games`, pesi, storico RF e `p_play`;
4. applicare una sola volta il DvP archiviato identico per entrambi, se il target è PDK finale; altrimenti confrontare PDK base in entrambi i rami;
5. verificare parità del replay operativo rispetto al PDK salvato prima di calcolare l’effetto shadow.

Calcolare MAE, RMSE e bias rispetto al PDK ufficiale per entrambi i rami e differenze appaiate (shadow minuti meno minuti operativi). Le righe senza target PDK ufficiale o con mapping ambiguo non entrano nelle metriche ma restano nel denominatore di coverage ed escluse con motivo. Outcome ufficiale mancante resta `pending`, mai zero.

### Incertezza e segmentazione

Per entrambe le metriche usare bootstrap appaiato a cluster per **giornata Dunkest** quando la mappatura gameweek/turno è verificata; altrimenti per data NBA (unità dichiarata). Ricampionare gli stessi cluster per i due metodi, almeno 2.000 repliche con seed registrato, riportando IC 95% della differenza MAE/RMSE/bias. Riportare risultati per giornata e pooled; con poche giornate gli intervalli saranno instabili e non si promuoverà il risultato.

Gruppi pre-lock, fissati prima di leggere gli outcome:

- **ruolo stabile:** team e `lineup_group`/ruolo invariati negli snapshot pre-lock consecutivi disponibili;
- **trasferimento/cambio squadra:** `team_changed_from_previous_game` nello storico pre-lock o team corrente diverso da precedente, secondo chiavi verificate;
- **minuti in crescita/in calo:** solo da delta storico disponibile al cutoff (`min_trend_3v5`, `min_last_vs_prev5`) con soglie prefissate su training/dev, mai dai minuti futuri;
- **rookie/low-history:** conteggio storico pre-lock archiviato, con definizioni preregistrate (ad es. zero, 1–5, 6–10 gare); non inferire dallo status successivo.

Se i campi necessari non sono salvati o i campioni sono insufficienti, la coorte va dichiarata non valutabile. Nessun gruppo definito dall’outcome postpartita.

## 5. Decisione e limiti

Non è possibile eseguire né descrivere risultati con i dati locali eleggibili: manca almeno il prerequisito fondamentale di un bundle pre-lock sotto il contratto corrente e un outcome ufficiale riconciliato. La procedura sopra non è stata eseguita e non genera metriche sostitutive.

Per dichiarare beneficio occorrono: replay operativo paritario, differenza shadow appaiata con intervallo cluster-bootstrap e copertura dichiarata; stabilità tra giornate e coorti; nessuna regressione rilevante nel PDK finale; più di un singolo run e holdout prospettico non usato per selezione. Anche un vantaggio sui minuti non dimostra da solo un vantaggio PDK. HGB rimane shadow finché non si soddisfano questi criteri.

## File e comandi

Codice letto: `src/dunkest/models/predictor.py`, `src/dunkest/features/minutes.py`, `src/dunkest/pipeline/predict.py`, `src/dunkest/pipeline/optimize.py`, `src/dunkest/report/artifacts.py`, `src/dunkest/data/dunkest/client.py`, `src/dunkest/data/dunkest/fixtures.py`, `scripts/archive_dunkest_pre_lock_run_v1.py`.

Comandi: `git status --short`; `rg -n` su minuti, replay, esiti e criteri; `sed` sui punti d’ingresso e funzioni; `find data/archives/pre_lock -name archive_manifest.json`; `find data -name 'post_match_*.parquet'`; script `python3` in sola lettura per riassumere stati/schema manifest e archivi formali. Nessun training, scraping, forecast o test è stato eseguito. `git diff --check` e controllo whitespace sul report sono stati eseguiti dopo la scrittura.
