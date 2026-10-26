# Dunkest 2.0 — audit dei segnali di minuti e cambiamenti di ruolo

**Data:** 2026-10-26
**Ambito:** ispezione statica del codice e degli artefatti/cache locali. Nessun training, scraping, forecast, test o modifica al modello è stato eseguito. La working tree era già modificata; l’unico file creato da questa operazione è questo report.

## Sintesi

Il predictor ha due livelli distinti che non vanno confusi:

- **Minuti operativi (`expected_min`)**: prior deterministico basato su minuti recenti/stagionali; quando il campione manca usa crediti Dunkest e annotazione Lineups (`QUINTETTO`/`PANCHINA`), con cap di ruolo, competizione nel roster, allocazione del budget minuti per ruolo e disponibilità. È questo valore, non l’output HGB, che entra nel ricalcolo operativo del PDK.
- **Minuti HGB (`expected_min_model_shadow`)**: modello ausiliario addestrato sul target storico `target_min`, esegue una predizione con le feature del predictor, viene registrato come shadow e non alimenta `expected_min`, il PDK operativo o il solver.

Sono disponibili segnali utili per forma e cambi di squadra, ma la pipeline non possiede una misura storica affidabile di titolarità/rotazione NBA: la titolarità pre-lock deriva dall’annotazione Lineups corrente; non c’è una feature di storico `NBA starter`. Non risulta una feature live di usage rate NBA. I timestamp dei cache correnti provano quando un intero file è stato acquisito, non quando ogni singolo dato storico è divenuto disponibile. Inoltre il run GW3 citato è incompleto/non eleggibile, quindi non è prova di accuratezza né copertura prospettica valida.

## Percorso effettivo

`pipeline/train.py` carica log NBA e storico precedente, applica l’overlay PDK ufficiale disponibile entro il cutoff, poi `features/builder.py::build_feature_matrix` produce le feature past-only, lo storico minuti e la riga d’inferenza. `pipeline/predict.py` carica listino/Lineups e indisponibilità, prepara i prior e chiama `predict_players`. In `models/predictor.py`, `train_models` addestra il modello PDK (con le feature candidate finite) e un HGB minuti shadow se sono disponibili almeno 200 `target_min`. `predict_players` calcola il PDK dell’ensemble, poi `expected_min` tramite `_base_minutes`, integra stato Lineups/infortuni, applica cap/competizione e ricalcola il PDK. Il valore HGB resta separato in `expected_min_model_shadow`.

## Feature e sorgenti verificate

| Segnale | Origine/trasformazione | Disponibilità al forecast e uso | Copertura/limiti |
|---|---|---|---|
| `lag1_nba_min`–`lag3_nba_min`, `prev3_nba_min_mean` | Log partita NBA per giocatore, `MIN`; ritardi/rolling con `shift(1)` in `features/builder.py::_rolling_features` | Feature del regressore PDK e input del modello minuti HGB. Past-only per data nel builder | Mancanti per giocatori senza log o righe invalide. Il source row non conserva un timestamp individuale d’acquisizione storico |
| `min_mean_5`, `min_mean_10` e `e_min_*` | Media minuti rolling o stagionale; le finestre sono shiftate. `features/minutes.py::expected_minutes_from_history` | `e_min_5` è la base principale di `expected_pdk_minutes_model`; la previsione operativa prende `e_min_5` e `e_min_season` in `_base_minutes` (65%/35% se entrambe) | Fallback dipende da disponibilità e `rolling_windows`; la feature storica `min_mean_10` è lasciata NaN dall’adapter multistagione |
| `min_trend_3v5`, `min_last_vs_prev5`, `abs_min_last_vs_prev5`, `min_std_5`, `min_zero_rate_5` | Delta/dispersione/tasso di zero su log minuti precedenti | Candidate features del regressore PDK e dell’HGB shadow | Sensibili a DNP/log mancanti e al cambiamento di squadra; non dimostrano la causa del cambiamento |
| `expected_pdk_minutes_model` | Prodotto di `e_min_5` per `pdk_per_min_season` (`combine_minutes_and_pdk_per_min`) | Feature candidata PDK. Nel trainer certificato storico l’adapter la pone a 0; quindi non equivale all’input dinamico live | Forte differenza tra storico adattato e live; il campo non è la previsione operativa `expected_min` |
| `team_changed_from_previous_game`, `team_history_known`, `team_games_since_change` | Cambio di `TEAM_ABBREVIATION` tra partite nel log NBA | Feature candidate PDK e shadow minuti; la pipeline corregge il team d’inferenza tramite override del mercato quando disponibile | Identifica solo cambio di squadra nel log, non cambio di ruolo o nuova opportunità. Storia incompleta/ID non riconciliati possono mancare |
| `lineup_group`, `starter`, ruolo e turno | Snapshot Dunkest Lineups/browser e mercato corrente, scelto per turno | `starter`/lineup non sono tutte colonne del regressore; `lineup_group` e crediti entrano nel prior minuti, cap e competizione operativi. Stato selezionato al turno della fixture | Solo prospettico per il momento di acquisizione; snapshot può essere incompleto/non verificato. Non è una serie storica di quintetti NBA |
| `cr`, `cr_change_last_gameweek` | Listino Dunkest corrente; variazione se presente nel mercato | `cr` alimenta il prior minuti e la competizione; la variazione è registrata nel forecast ma non è tra le feature candidate di `FEATURE_COLS` | La variazione è disponibile solo con snapshot/cronologia comparabile; non ricostruire da listini attuali |
| `p_play` e stato | Status Lineups e pagina ufficiale infortuni; la probabilità più prudente prevale | Riduce l’aspettativa finale con disponibilità e può azzerarla; non è la previsione di minuti condizionata alla presenza | Match di nomi/team prudente; valore/status dipende dal timestamp dello snapshot. Non distingue da solo DNP tecnico, riposo o limitazione di minuti |
| `history_games_before_target`, `nba_history_games_before_target`, `n_games`, `history_confidence` | Conteggio di righe/label storiche disponibili | Conteggi e confidenza supportano fallback/shrinkage; vengono salvati negli snapshot di previsione | Una riga NBA non equivale sempre a una partita Dunkest eleggibile; i contatori hanno definizioni diverse e non misurano timestamp di pubblicazione |
| `current_season_games`, `prior_seasons_games`, `pdk_per_min_current_season`, `pdk_per_min_prior_seasons` | Aggregazione delle partite precedenti, con PDK ufficiale dove verificato e minuti NBA | La produzione PDK mescola rate corrente e prior con shrinkage; non sono minuti | Dipende dalla copertura delle label ufficiali. Il solo backfill storico non certifica disponibilità al cutoff |
| Usage, starts/rotation NBA storici | Non individuata una feature NBA usage nel `FEATURE_COLS` live o nei log NBA usati dal predictor | Non usati come segnale operativo live. College rookie prior può avere `usage`/`starts_rate`, ma è un prior separato, solo per giocatori eleggibili | Non confondere usage da college con usage NBA; dati non presenti/non certificati per le coorti operative generali |

### Feature PDK che descrivono forma o opportunità, ma non minuti direttamente

`lag1_pdk`–`lag5_pdk`, `pdk_mean_*`, `pdk_std_5`, `pdk_trend_3v10`, `pts_mean_5`, `reb_mean_5`, `ast_mean_5` e rate per36 entrano nel regressore PDK. Sono segnali di produzione/forma; possono riflettere indirettamente un cambio di minuti, ma non separano causale “opportunità” da produzione per minuto. Restano invariati in produzione secondo il vincolo.

## Gestione attuale delle coorti

- **Ruolo stabile:** minuti storici pesano 65% recenti (`e_min_5`) e 35% stagionali quando entrambi disponibili; il rate PDK viene shrunk secondo il numero di gare. Il modello non calcola però un’etichetta esplicita di stabilità del ruolo.
- **Trasferito:** il cambio di team storico è una feature; l’override del team corrente aggiorna il contesto d’inferenza. `_base_minutes` non applica però uno specifico prior post-trasferimento. L’eventuale mismatch di identificativi può interrompere la continuità della serie.
- **Promosso/perde minuti:** trend e lag dei minuti sono candidate features del PDK/HGB; sul valore operativo agiscono inoltre lineup, crediti, competizione per ruolo e cap. La pipeline non etichetta esplicitamente una promozione o una perdita di ruolo e non ne certifica la causa.
- **Rookie/no storico:** `n_games` nullo è trattato come confidenza zero; il prior minuti usa CR e lineup, con cap più restrittivi per CR bassi. La rate può derivare da peer CR/ruolo, mercato storico del singolo o prior college (`rookie_college.csv`) con peso che decade con le gare. Questi fallback forniscono valori informativi ma sono stime/prior, non osservazioni. Se manca anche un prior valido, la rate può essere nulla e componenti sono riempite/gestite nei passaggi successivi: l’archivio registra `projection_source` e `history_source` per distinguerle.
- **Indisponibili/limitati:** la probabilità di presenza deriva dallo status; non è un modello di minuti condizionati alla presenza. Una limitazione di minutaggio non è necessariamente tradotta in un valore quantitativo se la fonte la descrive solo testualmente.

## Disponibilità e copertura locale osservata

Schema letto in sola lettura, senza ricalcolare forecast:

- `data/processed/player_game_logs_2025-26.parquet`: 24.100 righe, log NBA per partita con `PLAYER_ID`, `GAME_ID`, `GAME_DATE`, `MIN`, box score e team; metadata cache `fetched_at=2026-10-14T09:21:26Z`, raccolta dichiarata completa per 470 entità. È un’acquisizione successiva agli eventi storici, non prova pre-match per ciascuna riga.
- `data/processed/player_game_logs_2026-27.parquet`: 717 righe; metadata `source=nba_api/playergamelog`, `fetched_at=2026-10-25T10:08:30Z`, raccolta completa 335/335 entità. Contiene `MIN`, box score, `GAME_DATE`, `GAME_ID`, squadra e avversario, ma non starter o usage NBA. È una cache acquisita prima del cutoff del run GW3; il run GW3 stesso resta non eleggibile e non certifica forecast/OOS.
- `data/processed/team_game_logs_2026-27.parquet`: 72 righe, cache completa per 30 squadre acquisita `2026-10-25T10:08:43Z`. Fornisce contesto squadra, non rotazioni individuali.
- `data/current_lineups_market.csv`: 540 righe, campi nome/CR/team/role/lineup_group/starter/status/turn, acquisita `2026-10-25T10:08:28Z`. Non è un archivio storico di titolarità.
- `data/processed/injuries_26_gw3.parquet`: 83 righe, snapshot ufficiale con `observed_at_utc`, acquisito `2026-10-25T10:11:59Z`; fonte pre-lock del run GW3, ma non prova storico o affidabilità predittiva.

I conteggi sono righe dei file, non campioni di osservazioni forecast-outcome appaiate. Il run GW3 non è eleggibile; nessuna metrica di qualità dei minuti o di PDK per coorte è stata calcolata. Non sono stati trovati snapshot prospettici eleggibili con outcome ufficiali riconciliati per questo audit.

## Lacune principali

1. Nessun target-minuti live certificato e collegato per ID al forecast con lineup, CR, infortuni e cutoff originali.
2. Nessun timestamp per partita che provi quando furono osservati i log storici utilizzati in ciascun lag/rolling; l’ordine per `GAME_DATE` è un controllo event-time, non un acquisition-time proof.
3. Nessuna serie storica affidabile dei quintetti/starts NBA, ruolo Dunkest, availability/status e CR pre-lock per tutte le stagioni; non è possibile ricostruire coorti di promossi/declassati senza leakage.
4. Mancano usage NBA e misure storiche verificabili di limitazioni di minutaggio; i dati college del rookie prior sono proxy distinti.
5. HGB shadow e operativo `expected_min` non sono ancora confrontabili su una serie di bundle eleggibili con esiti riconciliati. Il valore shadow non va chiamato “minuti previsti dal modello live”.
6. Il risultato dei minuti non è sufficiente a dimostrare un miglioramento PDK: occorre ricalcolare la previsione con ciascuna alternativa mantenendo rate, disponibilità, DvP e altre componenti fisse, e poi valutare il PDK ufficiale.

## Esperimenti prospettici raccomandati

| Ordine | Esperimento (una domanda) | Baseline e variante appaiate | Misure/condizioni | Costo e rischio |
|---:|---|---|---|---|
| 1 | HGB shadow predice meglio i minuti del prior operativo? | Stesso forecast archiviato: `expected_min` operativo vs `expected_min_model_shadow`; per il test PDK, override minuti nella funzione condivisa tenendo fissi tutti gli altri input | Minuti: MAE/RMSE/bias tra minuti positivi, DNP separati e copertura; PDK: MAE/RMSE/bias appaiati sulle stesse righe; gruppi definiti ex ante da team-change, lineup/CR, trend e storico. Bootstrap per giornata | Basso-medio dopo raccolta dati; nessuna promozione automatica dello shadow. Richiede snapshot pre-lock e outcome minuti/PDK riconciliati |
| 2 | I segnali di transizione già disponibili aggiungono valore oltre al prior operativo? | Prior corrente vs variante shadow che usa soltanto informazioni archiviate al cutoff: variazione CR, lineup/status, `team_changed_from_previous_game`, trend minuti e copertura storico | Separare team change, promozione (lineup starter nuova con identificazione temporale), calo minuti e ruolo stabile; confronto paired sui minuti e sul PDK, senza definire gruppi usando outcome futuri | Medio; rischio leakage alto se storico pre-lock non è archiviato. Prima servono timestamp, lineup/CR pre-lock e regole di coorte preregistrate |
| 3 | Fallback per rookie/no-history è calibrato per le coorti con pochi log? | Rate/minuti operativi correnti e relative sorgenti (`cr_market_prior`, prior personale, college prior) confrontati con un solo fallback shadow predefinito per confronto | Valutare PDK/minuti, bias e code per 0, 1–5, 6–10 gare storiche; riportare fallback coverage. Non selezionare peso sul holdout | Medio; richiede archivio dei valori e pesi del prior usati prima del lock, più sufficienti rookie e outcome ufficiali |

Ogni esperimento deve partire soltanto dopo la comparsa di bundle pre-lock eleggibili, con feature/runtime snapshot, ID giocatore-partita, cutoff e hash validati; gli outcome NBA minuti e Dunkest PDK vanno aggiunti in un archivio separato e riconciliati senza modificare il forecast originario. Usare stessi esempi e giornata per baseline e variante, fold temporali prospettici, IC appaiati cluster-bootstrap per giornata e holdout non usato per selezionare parametri. Gli stati `DNP verificato`, `zero minuti`, `outcome non disponibile` e mapping ambiguo devono restare distinti; non imputare zero.

## Primo intervento raccomandato

**Sviluppare per primo l’esperimento prospettico di confronto `expected_min` operativo vs HGB shadow, con replay PDK a minuti alternativi.** È il confronto più informativo e circoscritto: sfrutta due valori già generati, non cambia il forecast operativo, separa errore minuti da valore PDK finale e può essere appaiato sullo stesso giocatore-partita. Il prerequisito è una nuova serie di bundle naturali eleggibili con outcome riconciliati; GW3 non può fornire questa evidenza.

Non raccomando di promuovere l’HGB o cambiare prior/pesi finché non si misurano errore, copertura e stabilità tra coorti e giornate.

## File e comandi ispezionati

Codice: `src/dunkest/features/builder.py`, `src/dunkest/features/minutes.py`, `src/dunkest/features/pdk_history.py`, `src/dunkest/models/predictor.py`, `src/dunkest/models/multiseason_training.py`, `src/dunkest/models/rookie_prior.py`, `src/dunkest/pipeline/train.py`, `src/dunkest/pipeline/predict.py`, `src/dunkest/data/access.py`, `src/dunkest/data/nba/collector.py`, `src/dunkest/report/artifacts.py`.

Dati letti: i log/cache NBA 2025/26 e 2026/27, team logs 2026/27, `current_lineups_market.csv`, snapshot injuries GW1–GW3, schemi dell’overlay Dunkest e metadata `.meta.json` associati. Nessun file dati è stato scritto.

Comandi: `git status --short`; `rg -n` mirati alle feature e alle funzioni; `sed` sui moduli sopra; piccolo script `python3` in sola lettura per schema, righe e metadata cache; nessun test necessario perché non è stato modificato codice. Nessun training, scraping, forecast, commit o push. `git diff --check` è stato eseguito dopo la creazione del report.
