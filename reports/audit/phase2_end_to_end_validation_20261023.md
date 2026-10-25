# Fase 2 — Validazione end-to-end Dunkest 2.0

Data controllo: 23 ottobre 2026, 15:12 UTC  
Branch: `codex/claude-audit-hardening-20261015`  
Esito complessivo: **non pronto per la produzione**. Le verifiche sugli artefatti storici e sui test sono utili, ma manca un forecast end-to-end alimentato da input validi al cutoff.

## 1. Forecast con fonti reali

Non è stato lanciato un nuovo forecast GW2 presentandolo come valido. La readiness del run reale più recente (`20261023T130830Z_b3191a4d`, target GW2) fallisce prima ancora di poter certificare i suoi output:

| Input | Evidenza del manifest | Stato |
|---|---|---|
| Fixture/matchup Dunkest | fixture mapping catturato dopo il lock; `fixture_mapping_source_verified=false` | Non valido al cutoff |
| Roster giocatori | snapshot mancante o acquisito dopo il lock | Non valido al cutoff |
| Crediti giocatori | snapshot acquisito dopo il lock | Non valido al cutoff |
| Infortuni | snapshot acquisito dopo il lock | Non valido al cutoff |
| Coach e matchup | snapshot acquisito dopo il lock | Non valido al cutoff |
| Disponibilità Lineups | snapshot vecchio di 195,9 ore, soglia 36 ore | Stale |
| Mercato Lineups | fresco, ma `all_eligible_lineups_verified=false`; il fixture `25/10 GSW @ PHX` non è verificato | Incompleto |
| Log giocatori NBA 2026-27 | Refresh ufficiale bulk del 23/10 14:53 UTC: 324 righe, 304 giocatori, 16 gare su 530 entità attive attese; raccolta completa | Disponibili nella cache corrente, ma acquisiti dopo il cutoff GW2 |
| Log squadre NBA 2026-27 | Refresh ufficiale del 23/10 15:07 UTC: 32 righe, 30 squadre, 16 gare, raccolta completa | Disponibili per il replay diagnostico; acquisiti dopo il cutoff GW2 |
| Target PDK Dunkest 2026/27 | Endpoint ufficiale `/stats/dunkest/week/rounds` restituisce `[]` per GW1 e GW2; cache GW1: 570 giocatori, 0 `actual_pdk`; cache GW2: 514 giocatori, 0 `actual_pdk` | Target ufficiale non ancora pubblicato; per la forma corrente resta il PDK proxy derivato dal box score NBA |
| Risultati per backtest | archivio post-partita hash-verificato non presente | Non disponibile |

Il primo tentativo seriale, con una richiesta per giocatore, è rimasto bloccato su una richiesta oltre diversi minuti ed è stato interrotto senza scrivere la cache. L’endpoint collettivo NBA `PlayerGameLogs` ha invece risposto in meno di un secondo. Il collector è stato aggiornato per usare questa richiesta bulk, mantenendo il controllo dei nomi non associati, la completezza e il merge persistente. Il refresh reale è riuscito due volte; la seconda esecuzione ha confermato l’idempotenza (324 righe, 324 identità giocatore/partita uniche, zero duplicati).

I risultati GW1 sono quindi disponibili per le giornate successive, ma la cattura è successiva al cutoff GW2 delle 12:00 UTC. Non li presento come uno snapshot pre-lock certificato né produco una rosa GW2 retroattivamente. Ho eseguito un replay diagnostico col trainer e predictor reali, usando gli snapshot post-cutoff locali; non equivale a un forecast integrale valido al lock e non ho eseguito l’ottimizzatore su questi input.

## 2. Robinson e campione di giocatori

L’artefatto del run GW2 contiene 414 previsioni, ma tutte hanno `has_history=false`; i campi `pdk_per_min_current_season` e `pdk_per_min_prior_seasons` sono NaN per tutti e 414. Il run usava il flag NBA disattivato e non rappresenta il codice aggiornato né la forma di stagione corrente.

| Caso nel run archiviato | Evidenza | Stato della verifica reale |
|---|---|---|
| Mitchell Robinson, storico precedente presente | La nuova cache contiene la gara `0022600001` del 20/10: 18,1 minuti, box score reale e 8,25 PDK proxy. La feature GW2 ha 1 gara corrente (0,4558 PDK/min proxy), 60 precedenti (0,9272 PDK/min), peso corrente 1/13 e tasso miscelato 0,8910 | Propagazione verificata su dati NBA reali fino alla feature passata al predictor. Nessuna rosa/forecast GW2 certificata al cutoff |
| Giocatori con gare 2026-27 | 324 righe reali di box score, 304 giocatori, 16 partite nelle date 20–22/10. Builder GW2: 420 righe d’inferenza; storia unita 24.424 righe (324 correnti + 24.100 precedenti), zero doppioni giocatore/partita | Forma reale verificata nel builder; il campione è post-cutoff per GW2 |
| Forma con campioni correnti multipli | LeBron James: 2 gare correnti e 60 precedenti; peso corrente 2/14; tasso 0,9179 PDK/min miscelato | Trade-off recente/storico verificato, coefficienti invariati |
| Scarso storico | Alex Morales ha 4 gare NBA storiche; il predictor usa `prior_seasons` e produce un PDK atteso finito | Verificato nel replay diagnostico con modello effettivo |
| Rookie | Kingston Flemings non ha gare NBA correnti né precedenti; il prior college produce 9,14 minuti, 0,7601 PDK/min e 6,95 PDK attesi | Verificato nel replay diagnostico con prior college reale. Il mercato era post-cutoff |
| Cambio squadra | Ja Morant: ultima squadra NBA storica MEM, mercato/corrente POR; 20 gare precedenti e 1 corrente, feature `current_and_prior_season_game_logs`, tasso miscelato 0,9181 | Cambio propagato nel replay; snapshot mercato post-cutoff |
| Indisponibilità/rischio DNP | Snapshot Dunkest locale: 51 `OUT`, 26 `GAME TIME DECISION`; fra i 458 giocatori con fixture verificata il predictor assegna `p_play=0` a 44 e `p_play=0,75` a 22. Cameron Johnson: 15,34 PDK condizionali, 11,51 attesi con `p_play=0,75` | Matematica verificata con snapshot post-cutoff, quindi non prova di una previsione pre-lock |

Mitchell Robinson nel replay col predictor di produzione: 22,66 minuti, 0,8910 PDK/min, 20,95 PDK condizionali e attesi, `p_play=1`; fonte `current_season_shrunk`, 1 gara corrente e 60 precedenti. Il peso corrente resta 1/13. L’output è diagnostico perché gli input GW2 sono post-cutoff.

Controllo temporale indipendente sulle 420 feature d’inferenza GW2: le date target sono 23 e 24/10; l’ultimo log NBA corrente è del 22/10. Zero target precedono o coincidono con l’ultimo log e zero conteggi `current_season_games` divergono dal ricalcolo per giocatore con filtro stretto `GAME_DATE < NBA_GAME_DATETIME_UTC`.

Non è stato usato alcuno stub. Il replay non viene dichiarato forecast valido né output finale per le rose.

## 3. Coerenza numerica del run archiviato

Per tutte le 414 righe del run archiviato:

- `expected_pdk_conditional = pdk_rate_for_projection × expected_min` (massimo errore assoluto: 0);
- `expected_pdk = expected_pdk_conditional × p_play` (massimo errore assoluto: 0);
- minuti, tasso, PDK condizionale e PDK atteso sono finiti; intervalli osservati rispettivamente 0,44–35,84 minuti, 0,239–1,714 PDK/min e 0,26–53,21 PDK condizionali.

Questi controlli verificano la contabilità delle colonne, non la correttezza della fonte del tasso: Robinson dimostra che una formula coerente può comunque usare un fallback non giustificato quando lo storico disponibile non è stato caricato. Nessun cap o coefficiente è stato modificato.

Nel replay diagnostico con dati correnti, trainer e predictor effettivi, la pipeline ha ridotto il mercato da 514 a 458 giocatori dopo il gate `mapping_verified=true` e `fantasy_eligible=true`; la fixture GSW–MEM non verificata è stata esclusa. Il trainer ha usato 93.766 righe con target PDK ufficiale 2020/21–2024/25 e zero righe GW1 proxy. Tutti i 458 output hanno minuti, tasso di proiezione, PDK condizionale e PDK atteso finiti; il tasso è composto da 260 `current_season_shrunk`, 126 `player_history_shrunk`, 43 `college_rookie_prior`, 27 `cr_market_prior` e 2 `prior_season_player_market_shrunk`. Minuti: 0–34,99; sono state filtrate 44 indisponibilità e sono rimasti 22 GTD al 75%.

Qui `expected_min × pdk_rate_for_projection` è la sola componente basata sul tasso. Il PDK condizionale finale combina anche ensemble, prior, modello storico e shrinkage per numerosità: la ricostruzione di questa formula completa coincide con `expected_pdk_conditional` (errore massimo `1,1e-14` nei valori salvati). `expected_pdk = expected_pdk_conditional × p_play` coincide anch’esso (errore massimo `1,8e-15`). La differenza fra il solo prodotto minuti×tasso e il totale non è quindi un errore aritmetico; confrontare il prodotto isolato con il totale sarebbe fuorviante.

Il replay è stato salvato in [diagnostic_predictor_replay_gw2_postcutoff_20261023.csv](diagnostic_predictor_replay_gw2_postcutoff_20261023.csv) e [diagnostic_predictor_replay_gw2_postcutoff_20261023.json](diagnostic_predictor_replay_gw2_postcutoff_20261023.json). Snapshot mercato e infortuni risalgono al 23/10 13:08 UTC, dopo il lock: non sono usati per certificare selezioni o rose.

## 4. Aggiornamento progressivo

Stato osservato nel run GW2 archiviato: 0 log NBA correnti e `use_nba_api_logs=false`. Quello specifico run non acquisì né salvò le statistiche della GW1. Nel controllo corrente la cache ufficiale ha 324 righe giocatore/partita, 16 gare, 304 giocatori, 0 doppioni e metadata `collection_complete=true` (530/530 entità, 0 errori, 0 troncamenti). Tutti i 16 `GAME_ID` NBA acquisiti corrispondono uno-a-uno a fixture GW1 `mapping_verified=true` e `fantasy_eligible=true`; zero ID non mappati o non verificati. I log squadra coprono gli stessi 16 ID. Primo refresh: 324 righe acquisite, 324 aggiunte, 0 aggiornate, 0 conservate, 0 duplicate/scartate. Secondo refresh reale: 324 acquisite, 0 aggiunte, 324 aggiornate, 0 conservate, totale 324 uniche. Le feature GW2 hanno usato tutte le 324 righe correnti e aggiunto 24.100 righe storiche certificate; lo snapshot è stato raccolto alle 14:53 UTC, dopo il cutoff. Per la GW2 non sono ancora disponibili risultati post-partita da conteggiare.

Stato codice: il collector ora usa una singola richiesta NBA bulk al posto delle centinaia di richieste seriali; i test mirati di integrità raccolta e storico corrente hanno dato **17 passed**. La suite completa eseguita dopo la modifica ha dato **650 passed**. Sono state salvate anche 32 righe di log squadra per 30 team e 16 gare; raccolta completa, zero errori. È verificato con dati reali il percorso `NBA API → cache completa → storia precedente+corrente → feature → predictor` e la formula di blending. Il replay ha usato trainer multi-stagione e predittore reali, senza target proxy nel training. Non è stato eseguito un forecast pre-lock né l’ottimizzatore di produzione: gli snapshot GW2 non sono validi al cutoff.

La PDK NBA della cache resta un proxy calcolato dal box score tramite le regole locali: gli aggregati GW1/GW2 non hanno `actual_pdk`. Nella sezione 8 aggiungo un collegamento conservativo tra i PDK ufficiali per turno e i log NBA: serve una firma univoca di nome, squadra e otto statistiche di box score, oltre alla prova che lo snapshot preceda il cutoff target. Il blending recente/storico non cambia; le etichette ufficiali passano attraverso la serie già usata per le feature laggate e il relativo shrinkage esistente.

Controllo read-only delle 15:16 UTC: `fetch_week_rounds` configurato con l’ID locale `26` ha restituito `[]` per GW1 e GW2; quel controllo non aveva selezionato il catalogo ufficiale corretto. I parquet aggregati mantengono comunque `gameweek_stats_available=false` per tutte le 570 righe GW1 e 514 righe GW2, con zero `actual_pdk` valorizzati; la correzione non trasforma questi aggregati in target PDK per-partita.

## 5. Backtest e copertura dati

Inventario dei dati disponibili:

- Dunkest ufficiale 2018-19–2024-25: 172.098 righe e 1.077 giocatori; il campo `gameValidForDunkest` è falso per tutte le 26.094 righe 2018-19 e tutte le 22.384 righe 2019-20. Non sono target utilizzabili senza chiarire quella semantica.
- Target ufficiali validi 2020-21–2024-25: 93.766 righe complessive.
- File Dunkest 2025-26: 27.706 righe; 21.889 con `gameValidForDunkest=true`.
- Dataset walk-forward già costruito 2020-21–2025-26: 112.178 righe, di cui 18.412 nel test 2025-26. È un sottoinsieme abbinato e utilizzabile per il backtest individuale PDK.
- I log NBA storici 2018-19–2024-25 sono disponibili; manifest di raccolta: 7 stagioni complete, 24.100–26.401 righe per stagione e zero errori di acquisizione.

Ho inoltre eseguito un holdout 2025-26 con il trainer `train_models` effettivo della pipeline: 93.766 righe ufficiali valide 2020/21–2024/25 per training, 18.412 righe 2025/26 per test, nessun target 2025/26 usato nell’addestramento. Le feature di ciascuna riga test usano soltanto partite precedenti. Non sono stati cambiati parametri o pesi.

Ho ricalcolato le metriche dai 18.412 output salvati e coincidono con l’audit JSON. Nel test: 0 doppioni per giocatore/partita, 0 doppioni per giocatore/data, 0 feature NBA associate alla stessa data o a una data futura; 0 output PDK non finiti.

| Modello | N | MAE | RMSE | Bias predetto − osservato | R² |
|---|---:|---:|---:|---:|---:|
| Ensemble trainer produzione | 18.412 | 7,5149 | 9,7659 | −0,0126 | 0,4320 |
| Baseline media ultime 10 gare | 18.412 | 7,7886 | 10,1539 | −0,0479 | 0,3859 |

L’ensemble riduce MAE del 3,5% e RMSE del 3,8% rispetto alla baseline, con bias medio leggermente più lontano da zero. La calibrazione per decili mostra bias medio da −0,419 a +0,417 PDK. Non sono stati prodotti intervalli P10/P90 indipendenti per questo test. La copertura P10/P90 nel manifest del run GW2 è calcolata su predizioni cross-fitted e residui stimati sullo stesso campione OOF: diagnostica, non prova indipendente di calibrazione.

Questo è un test individuale PDK, non il backtest di una rosa reale pre-lock. L’audit riproducibile e i valori per decile/mese sono in [production_trainer_holdout_2025-26_20261023.md](production_trainer_holdout_2025-26_20261023.md); sono salvati anche previsioni e JSON completi.

Ho eseguito `PYTHONPATH=src ./.venv/bin/python -m dunkest backtest --from-gw 1 --to-gw 2`: exit 2, nessuna metrica lineup prodotta. La GW1 ha i snapshot PRE_MATCH richiesti (fixture, roster/prezzi, infortuni e coach) ma fallisce la disponibilità Lineups stale di 197,3 ore e manca l’archivio dei risultati verificati. La GW2 fallisce fixture mapping post-lock, roster, prezzi, infortuni e coach acquisiti dopo il lock, disponibilità stale e risultati mancanti. Il backtest lineup storico richiesto 2018-19–2025-26 non è certificabile: non ci sono snapshot pre-lock e archivi risultato fixture-linked hash-verificati per quelle stagioni. Non ho ricostruito snapshot retroattivi.

## 6. Formazioni archiviate

Controllo ricalcolato sui 30 record di `lineups.parquet` del run GW2 archiviato. Questo è un controllo di coerenza matematica dell’output generato, non una conferma che input e previsioni fossero validi al cutoff.

| Rango | Giocatori unici | Budget / 96,1 | Modulo per turno | Lordo ricalcolato | Malus trasferimenti | Netto ricalcolato |
|---:|---:|---:|---|---:|---:|---:|
| 1 | 10 | 96,1 | 1-2-2 / 1-2-2 | 223,4053 | 15 | 208,4053 |
| 2 | 10 | 96,0 | 1-2-2 / 1-2-2 | 233,2316 | 25 | 208,2316 |
| 3 | 10 | 95,7 | 1-2-2 / 1-2-2 | 227,6612 | 20 | 207,6612 |

Tutti e tre i solver status sono `Optimal`; ogni roster rispetta 5 slot attivi, 1 sesto uomo e 4 panchinari per turno, il capitano è assegnato al turno di gioco, non ci sono promozioni dalla panchina dopo il turno di un giocatore, le moltiplicazioni di punteggio coincidono e i netti ricalcolano come lordo meno `5 × trasferimenti`. Le tre rose differiscono a coppie di 4, 2 e 2 giocatori. La verifica include coach e relativo costo nel budget; nessun limite squadra viene superato.

## 7. Conclusione operativa

**Verificato con dati reali:** integrità aritmetica delle previsioni del vecchio run; tre formazioni archiviate e loro score accounting; holdout walk-forward 2025-26 del trainer di produzione, baseline e calibrazione per decile; copertura dei dataset e del flag di validità.

**Verificato solo con dati sintetici/test:** aggiornamento GW2→GW3, rifiuto dei dati oltre cutoff e conservazione della cache dopo un refresh vuoto. GW1→GW2 e l’idempotenza GW1 sono stati inoltre verificati con dati reali post-cutoff (324 righe, nessun duplicato); questo non certifica un forecast GW2 pre-lock.

**Verificato con dati reali:** statistiche NBA GW1 e log squadra nella cache; propagazione di GW1 nelle feature e nel predictor multi-stagione effettivo; gate fixture verificato (15 fixture, GSW–MEM esclusa); controlli di campione su Robinson, rookie, storico scarso, cambio squadra e indisponibilità (questi ultimi con snapshot post-cutoff); identità matematiche del replay; holdout 2025/26 e coerenza delle rose archiviate.

**Non verificabile ora:** forecast e ottimizzazione GW2 pre-lock; join uno-a-uno dei nuovi PDK per turno GW1 con i log NBA; previsioni di disponibilità con snapshot acquisiti prima del cutoff; backtest lineup storico con snapshot e risultati verificati.

Il progetto non va considerato pronto per la produzione finché non vengono catturati fixture/roster/crediti/infortuni/coach prima del lock e non si esegue un forecast reale con controlli essenziali sulle formazioni. L’acquisizione progressiva della forma NBA è verificata. La tabella ufficiale contiene ora PDK per turno GW1, insieme a CR e PLUS; questi risultati sono stati acquisiti dopo il cutoff GW2, non sono ancora riconciliati uno-a-uno con i log NBA e non certificano gli input pre-lock GW2.

## 8. Correzione catalogo Dunkest e archivio ufficiale per turno

La pagina [NBA Stats di Dunkest](https://www.dunkest.com/en/nba/stats/players/table?iframe=yes) dichiara la stagione Regular Season 2026/27 con `season_id=29`, mentre il progetto usa `season_id=26` per nominare i propri artefatti NBA. `dunkest_stats_season_id` ora mantiene esplicitamente questa distinzione in configurazione e il client la applica a catalogo, stats table, mercato NBA e coach. La tabella ufficiale è stata acquisita direttamente dal browser impostando `mode=dunkest`, `stats_type=tot`, `weeks[]=1`, il singolo `rounds[]`, tutte le squadre/posizioni e la fascia CR 4–35.

| Turno GW1 | Righe giocatore | Squadre presenti | PDK / CR / PLUS non nulli | Acquisizione UTC |
|---:|---:|---:|---|---|
| 1 | 68 | 6 | 68 / 68 / 68 | 2026-10-23 15:28 |
| 2 | 251 | 22 | 251 / 251 / 251 | 2026-10-23 15:29 |
| 3 | 22 | 3 | 22 / 22 / 22 | 2026-10-23 15:22 |

Per ciascun turno sono presenti un JSON grezzo con filtri, fonte, ID catalogo, timestamp e nota temporale, e un parquet processato con PDK ufficiale Dunkest, CR, PLUS, minuti, titolarità e statistiche base. File: `data/raw/dunkest_stats_season29_week1_round{1,2,3}_20261023.json` e `data/processed/dunkest_stats_26_gw1_round{1,2,3}.parquet`. I campi CR sono quelli restituiti dalla riga ufficiale selezionata per quel turno e l’archivio conserva la prima acquisizione; il timestamp locale documenta quando li abbiamo osservati. Non si presume che tali righe dimostrino uno snapshot pre-lock GW2.

Il collector automatico archivia ora PDK/CR/PLUS e box score per ciascun turno già concluso quando prepara una giornata successiva; l’archivio è write-once per non sostituire il primo valore CR osservato con un successivo refresh. Sono aggiunti test per ID stagione distinto, filtro esatto del turno, conservazione write-once e raccolta GW1 durante il run GW2. Il refresh live via shell non è stato possibile per la risoluzione DNS della sessione: l’acquisizione manuale via pagina/feed ufficiale è completa per i dati sopra indicati. Il round 3 ha copertura di sole 3 squadre nella cattura disponibile e non viene dichiarato completo come copertura di risultati della giornata.

Il blending già validato fra stagione corrente e storico resta invariato. La nuova riconciliazione ha trovato 281 collegamenti univoci su 319 righe dei round GW1 1–2 (zero ambigui, 38 senza firma corrispondente). La cattura ufficiale è del 23/10 alle 15:28–15:29 UTC; rispetto al cutoff GW2 delle 12:00 UTC il join accetta zero righe. Una prova con cutoff ipotetico successivo alla cattura trova tutti i 281 match e conferma che il builder preferisce questi PDK ufficiali al proxy come input storico. È una verifica della regola di propagazione, non un forecast GW3: manca un bridge GW3 verificato con NBA GAME_ID e gli input Lineups aggiornati. I round 3 restano fuori perché lo snapshot disponibile non ha i campi del box score necessari.

Aggiornamento read-only dei feed ufficiali alle 15:40–15:41 UTC: la config lega indica GW2 (matchday 1859), il cui primo round inizia alle 19:59 UTC; la GW2 espone i round `1` e `2`, ma la tabella `tot` per il round 1 restituisce `[]`. Non è quindi ancora disponibile un risultato Dunkest da archiviare per la giornata in corso. La config pubblica anche il matchday GW3 (ID 1860): 17 partite distribuite su tre round, prima partita il 25/10 alle 21:00 UTC. La cache NBA locale contiene lo schedule del 7/10 e il mapping Lineups salvato arriva solo alla GW2; non li ho usati per creare un bridge GW3 di produzione. Il collector ora registra un warning esplicito per il feed Stats vuoto e non crea snapshot PDK/CR vuoti; non tratta l’assenza del dato come un aggiornamento completato.

`attach_observed_round_pdk_labels()` legge questi snapshot al training, abbina solo record con nome canonico e squadra concordanti e uguaglianza su PTS/AST/REB/STL/BLK/OREB/DREB/TOV. Richiede inoltre `observed_at_utc` precedente al timestamp minimo del mapping verificato della giornata target; record mancanti, ambigui o conflittuali restano esclusi. Per GW2 lo zero accettato è intenzionale: i dati furono osservati alle 15:28 UTC, dopo il cutoff delle 12:00 UTC; anche il timestamp minimo del mapping GW2 (00:00 UTC del 23/10) è precedente alla cattura. Il mapping non registra l'orario esatto di lock Dunkest: la soglia schedule è un limite prudenziale, non una certificazione autonoma del cutoff di ogni giornata. Per una giornata futura, `PDK_OFFICIAL_VALID` alimenta le feature di forma esistenti solo quando precede tale limite e le fixture sono disponibili; `cr` e `plus` restano archiviati per giornata/turno come valori osservati, senza essere retrodatati. I pesi di blending non sono stati cambiati.

Verifica finale aggiornata: `PYTHONPATH=src .venv/bin/pytest -q` → **660 passed** (suite rilanciata dopo il controllo sintetico GW1→GW2→GW3 e la diagnosi di scraping vuoto), con un warning non bloccante di joblib sul conteggio dei core; `git diff --check` senza errori. I nuovi test coprono join box score esatto, propagazione del PDK ufficiale nel builder, esclusione post-cutoff, mancata corrispondenza, ambiguità, aggiornamento progressivo di PDK/CR tra giornate e feed vuoto senza snapshot falso. Gli input GW2 post-cutoff restano esclusi dalla certificazione di una rosa GW2 pre-lock.

## 9. Forecast pre-partita GW2 (23 ottobre, aggiornamento successivo al cutoff congelato)

Su indicazione dell'utente ho eseguito `PYTHONPATH=src .venv/bin/python -m dunkest run --giornata 2 --roster config/current_roster.yaml --no-lineups-scrape`. Il run completo è terminato alle **16:03 UTC**, prima del primo round GW2 (19:59 UTC secondo il calendario ufficiale già consultato). Artefatti: `data/predictions/20261023T160312Z_70776819/`. Nessun risultato GW2 è entrato nel run: il market Stats è marcato `gameweek_stats_available=false` e `actual_pdk` è nullo per tutte le righe.

Al cutoff di questo run erano disponibili 324 righe giocatore per 16 partite NBA GW1 (cache NBA completa, catturata 14:55 UTC), 32 righe squadra per 16 partite (15:07 UTC), la tabella Dunkest/crediti GW2 da 514 giocatori (13:08 UTC), Lineups con 514 giocatori e 29 coach, e 77 stati infortuni ufficiali aggiornati alle 16:02 UTC. Il calendario catturato comprende 16 fixture: 15 con mapping NBA verificato e una non verificata; nessun giocatore delle tre rose selezionate appartiene alla fixture non verificata. Ogni coppia giocatore-squadra-avversario-turno selezionata è stata ricollegata a una fixture verificata.

Il refresh live ha incontrato un errore DNS. Ho corretto la pipeline affinché riusi una cache NBA soltanto se fonte, completezza, freschezza (massimo 24 ore), chiavi e assenza di duplicati sono verificate. In previsione può riutilizzare la tabella Stats GW2 solo se è una cattura della stessa giornata entro la freschezza configurata, con almeno 250 righe e senza PDK effettivi GW2; non le cambia il timestamp né risalva il market come nuovo. Il report infortuni dello stesso GW è riutilizzabile solo se fresco. In questo run il modello di training e predictor non è stato stub-bato: le statistiche GW1 sono passate nelle feature e il trainer reale è stato eseguito.

Mitchell Robinson: 60 gare di storico 2025/26 e 1 partita NBA GW1 sono arrivate al predictor; `history_source=current_and_prior_season_game_logs`, `projection_source=current_season_shrunk`, PDK/min corrente 0,456, storico 0,919, tasso per proiezione 0,891, minuti 22,66 e PDK attesi 20,95. Nessun coefficiente è stato ritarato.

Le tre soluzioni sono state `Optimal`, con 10 giocatori, 4 titolari, sesto uomo, 4 panchinari, coach incluso e budget rispettivamente 95,6 / 96,0 / 96,1 CR. Il PDK netto ricalcola come lordo meno `5 × trasferimenti` (20 / 15 / 20). Le rose 1 e 2 differiscono di soli **0,25 PDK previsti netti**; la rosa 2 richiede un trasferimento in meno.

| Rango | Dentro | Fuori | Trasferimenti | CR usati | PDK netto previsto |
|---:|---|---|---:|---:|---:|
| 1 | LeBron James, Mitchell Robinson, Kyrie Irving, Isaiah Jackson | Evan Mobley, Jarrett Allen, Ty Jerome, Zaccharie Risacher | 4 | 95,6 | 195,08 |
| 2 | LeBron James, Mitchell Robinson, Kyrie Irving | Evan Mobley, Jarrett Allen, Ty Jerome | 3 | 96,0 | 194,83 |
| 3 | LeBron James, Mitchell Robinson, Kyrie Irving, Ziaire Williams | Evan Mobley, Jarrett Allen, Ty Jerome, Zaccharie Risacher | 4 | 96,1 | 193,09 |

**Indicazione per la rosa attuale:** il rango 2 è il compromesso preferibile: cedere Evan Mobley, Jarrett Allen e Ty Jerome; prendere LeBron James, Mitchell Robinson e Kyrie Irving; mantenere gli altri sette giocatori e coach Micah Nori. Il rango 1 massimizza il valore atteso, ma il vantaggio di 0,25 PDK non compensa bene il trasferimento aggiuntivo secondo il punteggio netto previsto. Sono suggerimenti del modello, non risultati realizzati.

Limite di audit: nel file `lineups.parquet` i 30 campi `nba_game_id` dei giocatori sono nulli, benché avversario e turno si colleghino univocamente alle fixture verificate. La validazione della rosa è stata quindi fatta via squadra-avversario-turno; va aggiunta la propagazione diretta dell'ID NBA negli artefatti lineup. Inoltre il run è successivo alle 12:00 UTC e non sostituisce il forecast prospettico congelato a quel cutoff; documenta invece una previsione GW2 a 16:03 UTC con soli input pre-tipoff.

I test mirati sono **32 passed**; la suite completa dopo le correzioni è **663 passed, 1 warning non bloccante joblib**, e `git diff --check` è pulito.
