# Dunkest 2.0 — audit data-driven del predictor e piano sperimentale

**Data:** 2026-10-26. **Ambito:** audit statico del codice e sintesi verificata di dataset/report già presenti. Nessuna modifica a predictor, pesi, optimizer o dati; nessun training, scraping o forecast. Il run `20261025T101251Z_6d20853d` è trattato come diagnostico non eleggibile.

## Sintesi decisionale

Il progetto dispone di un buon archivio storico per valutazioni PDK player-game: 112.178 righe supervisionate nel training table 2020/21–2025/26, target ufficiali Dunkest validi, bridge NBA per 112.165 righe, e un holdout salvato 2025/26 da 18.412 coppie. La pipeline live usa un modello di regressione PDK, una stima di minuti separata per shadow, priors di roster/CR e lineup, correzione DvP post-predizione e un solver congiunto di giocatori e coach.

Le evidenze più solide già disponibili sono: l'arricchimento lagged ha ridotto l'errore nelle valutazioni temporali storiche; la storia PDK ufficiale invece non ha mostrato un vantaggio statisticamente conclusivo sul proxy; il modello HGB minuti migliora le metriche dei minuti rispetto a last-5 ma la sua applicazione ai punti peggiora PDK e resta correttamente in shadow. Il RF storico sui punteggi alti e il test 2025/26 mostrano una regressione nella coorte definita dall'outcome, ma non rappresentano automaticamente il predictor live.

Il limite prioritario non è una feature mancante: è l'assenza di una sequenza di bundle live eleggibili e outcome ufficiali riconciliati. Il run GW3 citato non può essere usato come OOS: mancano ID Dunkest stabili per 148 candidati, il manifest marca il runtime incompleto e non esiste un `archive_manifest.json` o outcome riconciliato. Non si deve ricostruire quel run.

**Decisione:** nessuna modifica al modello è giustificata da questo audit. Il prossimo lavoro con più valore informativo è chiudere la raccolta prospettica con identità stabili e outcome separati; in parallelo, usare solo i fold di sviluppo non riservati per un'analisi mirata dei residui di ruolo/minuti già rappresentati nel dataset storico.

## 1. Percorso operativo ricostruito

1. `pipeline/train.py::run_train` acquisisce/legge i log NBA giocatore e squadra, applica overlay PDK ufficiali quando validi e costruisce la matrice con `features/builder.py::build_feature_matrix`. Dopo GW1 unisce log prior-season certificati e log della stagione corrente; le feature future sono filtrate rispetto al cutoff di schedule disponibile, con il limite che l'orario kickoff è una soglia prudenziale e non equivale sempre all'esatto lock Dunkest.
2. `features/builder.py` calcola statistiche rolling e laggate (shift pre-target), minuti storici, trend, forma PDK, contesto avversario, riposo/B2B/casa, storico contro avversario e segnali di cambio squadra/volatilità minuti. Le fonti di disponibilità e il mercato corrente sono contesto operativo distinto dai risultati NBA passati.
3. `models/predictor.py::train_models` usa l'intersezione fra colonne presenti e finite in `FEATURE_COLS` (68 nomi candidati nel file attuale; il numero realmente usato varia per training). Allena il regressore sul PDK target selezionato, mantiene gli input mancanti/imputazione secondo lo schema, usa pesi OOF temporali per ensemble/proiezione e allena un modello HGB separato sui minuti osservati.
4. `predictor.py::predict_players` trasforma le stime in PDK condizionale/finale, applica stime operative di minuti/ruolo e probabilità di presenza, usa prior di mercato/ruolo e rookie per i record con poco storico e costruisce incertezza/plusvalenza. Il minuto HGB resta shadow; `pipeline/optimize.py::run_optimize` rimuove `expected_min_model_shadow` prima di chiamare il solver.
5. `pipeline/predict.py::run_predict` associa fixture, mercato e indisponibilità verificate; seleziona DvP pre-cutoff e applica la correzione al PDK dopo l'inferenza, senza inserirla nella probabilità coach. Se DvP manca/non è valido, mantiene il PDK base e registra il fallback.
6. `optimize/milp.py::optimize_top_k_lineups` ottimizza insieme giocatori e coach con budget, ruoli, limiti squadra, slot, capitano e diversificazione top-3. L'obiettivo usa PDK con i moltiplicatori di ruolo/regole; se configurato, applica risk adjustment, include valore atteso plusvalenza tramite shadow price di budget e sottrae malus trasferimenti. Quindi il valore del roster non è un ranking individuale PDK/CR.
7. `report/artifacts.py::save_run_artifacts` salva output e snapshot con schema/hash/metadati e stato di completezza. Archiviatore e reviewer richiedono più dei file presenti; l'outcome viene aggiunto successivamente in un archivio separato. Le anomalie identificate sul run GW3 sono documentate nel report di persistenza e in quello di eleggibilità, senza usare il run per misurare prestazioni.

## 2. Inventario di fonti e copertura disponibile

I numeri locali sotto riprendono l'inventario dataset eseguito il 2026-10-26 e sono riportati nei file referenziati. La cartella `data/` è locale/esclusa dal controllo versione; la presenza del file non certifica da sola provenienza point-in-time.

| Fonte reale | Artefatti/codice e copertura locale | Uso live attuale | Limite temporale, join e valore analitico |
|---|---|---|---|
| PDK ufficiali per giocatore-partita | `official_dunkest_player_games_2018-25_v1.parquet` (172.098 righe su 7 stagioni; validità target storiche miste); `official_dunkest_player_games_2025-26.parquet` (27.706 righe, 527 ID, 21.889 flag validi); training table `dunkest_pdk_game_training_2020-26_v3.parquet` (112.178 righe; 112.165 bridge NBA). | Target supervisivo e, se catturati e joinati in modo univoco prima del target, lag PDK. | Target valido solo con `gameValidForDunkest=True`. Join valido ma non universale; mancano 13 collegamenti nel training table. Le acquisizioni successive alla partita non sono feature pre-lock.
| Log NBA giocatore | Raw 2018–25 e processed 2024/25–2026/27; raccolta in `data/nba/collector.py`, accesso in `data/access.py`; 2025/26 match ufficiale 18.412; 2026/27 locale 717 righe in 5 date. | Minuti e box score passati, statistiche per possesso/minuto, matchup e target minuti shadow. | ID NBA stabili; bridge Dunkest basato in parte su giocatore/data/avversario. Box score PDK è proxy e non contiene sempre bonus Dunkest (ad es. starter). La stagione 2026/27 ha pochissime gare.
| Log NBA squadra/fixture | `team_game_logs_2018-26_v1.parquet` (19.038 team-game); fixture verificati per GW1–GW3 con NBA game ID, turni, data e provenienza. | Contesto opp rating/pace/rimbalzi, casa/trasferta, margine/coach e fixture. | Calendario NBA e Dunkest non sono chiavi intercambiabili; fixture storico multi-stagione/as-of incompleto.
| Mercato, ruolo e Lineups | `current_lineups_market.csv`; snapshot `player_credits_26_gw1/2/3`, mercato Dunkest e coach; browser collector in `lineups_browser.py`. | CR, ruolo, squadra, lineup group e roster candidato del forecast corrente. L'identità è mappata/arricchita dal pool stats Dunkest quando disponibile. | Catture affidabili solo per le giornate presenti; CSV Lineups può non contenere ID ufficiali. Nel GW3 148/519 ID sono nulli. Non c'è storico multistagione di mercato al lock certificato.
| Infortuni/disponibilità | `injuries_26_gw1/2/3.parquet`, metadati e scraper ufficiale injuries; `play_probability` viene derivata dal testo stato/lineup. | Corregge probabilità di presenza e dunque PDK atteso; non è un'etichetta di partecipazione appresa da storico live. | Solo 2026/27 e pochi snapshot; nessun panel storico pre-lock verificato. Non si può stimare un effetto storico delle assenze dei compagni senza leakage.
| DvP | `data/processed/dunkest_dvp/29/`: sei snapshot validi completi da 2.880 righe ciascuno (30 team × 3 posizioni × 8 statistiche × 4 finestre); una cattura fallita. | Correzione PDK player separata e post-predizione; 65% ALL, 20% L10, 10% L5, 5% L3, cap configurato al 2%. Non è feature del regressore PDK e non entra direttamente nelle probabilità coach. | Solo catture del 25–26 ottobre 2026; 896/2.880 valori sono cambiati tra due snapshot. Non esiste serie storica pre-lock per backtest DvP.
| Rookie | `data/rookie_college.csv` e `data/rookie_official_pdk.csv` (264 giocatori, classi 2020–25). | Prior rate/minuti rookie con peso che decade in funzione dello storico osservato; target ufficiale se la copertura soddisfa il gate, altrimenti fonte proxy distinta. | Coorti limitate, ID/draft mapping da controllare. Non esiste outcome 2026/27 sufficiente per validare il prior attuale.
| PDK/CR/PLUS weekly-turn | `dunkest_historical_player_week_round_2020-25_v2.parquet` (93.785 righe, cinque stagioni); PLUS history multiseason (93.744 righe). | Forma/mercato storico e modello plusvalenza. | PDK aggregato al turno non equivale a una singola partita NBA; CR stesso turno senza timestamp lock non è un prezzo pre-lock certificato.
| Coach | Coach market/forecast current in alcuni bundle; log squadra storici e report di probabilità/margini. | Forza matchup/margine, probabilità win e PDK coach; il solver sceglie coach con rosa e budget. | Mancano prezzi coach storici as-of e archivio riconciliato di PDK coach ufficiale; test team-point non certifica il PDK fantasy con coefficiente di quotazione.
| Forecast e outcome prospettici | 115 run dirs e 1.313 file in `data/predictions/`; 17 bundles GW1–GW3 in `data/archive/26/`. | Snapshot candidati, feature runtime, shadow minuti, coach, input, versioni/hash; reviewer/gate outcome separati. | Stato di eleggibilità eterogeneo; non sono stati trovati outcome ufficiali post-match collegabili per i run nell'inventario. Il GW3 diagnostico resta escluso.

Fonti, forme dei dati, endpoint già implementati e limiti sono dettagliati in `reports/audit/dunkest_data_inventory_opportunity_audit_20261026.md`. Gli endpoint ufficiali descritti dal client sono `/api/stats/table`, `/api/stats/dunkest/week/rounds` e la raccolta della pagina injuries via browser; la verifica HTTP di sola lettura già registrata quel giorno fallì per DNS locale prima di ottenere risposta. Non considero questo un fallimento permanente della fonte né ho ripetuto richieste.

## 3. Feature: utilizzate, separate, non utilizzabili per tuning attuale

### Feature che arrivano al regressore PDK

Nel `FEATURE_COLS` corrente sono presenti:

- PDK storico: rolling mean/mediana/deviazione, lag 1–5, trend 3v10;
- minuti: rolling 5/10, lag 1–3, media 3, trend 3v5, ultimo vs media 5, volatilità e frequenza zero;
- produzione box score: punti/rimbalzi/assist recenti, rate per 36 di recuperi/stoppate/turnover/rimbalzi/triple, percentuali tiro;
- matchup: riposo, B2B, casa, contesto avversario recente (punti concessi, plus/minus, def rating, pace, rimbalzi difensivi), storico giocatore contro avversario;
- stabilità/identità: squadra cambiata, storia squadra nota, partite dalla transizione, numero di partite di storia NBA e Dunkest.

La feature generation è past-only per rolling/lag. Il predictor usa `FEATURE_COLS` finite: una colonna calcolata può essere esclusa perché assente o tutta nulla nell'addestramento, e le colonne descrittive/ID non sono predittori.

### Componenti che incidono fuori dal regressore

- Il minuti operativo `expected_min` deriva da storico, CR/ruolo, lineup/availability e allocazione per posizione; è usato nel ricalcolo PDK insieme a pesi di proiezione appresi. HGB è addestrato su `target_min` ma esposto come `expected_min_model_shadow`; non sostituisce il minuto operativo e non viene passato al solver.
- Disponibilità `p_play` è una correzione runtime del PDK atteso, non un classificatore DNP calibrato su serie storiche point-in-time.
- I prior di mercato per CR/ruolo/giocatore e il prior rookie sono fallback/shrinkage di rate e minuti. I prezzi storici non validano un backtest di roster se non sono as-of.
- DvP è un correttore post-modello. Quindi il modello non impara a stimarne l'effetto e la copertura completa di un singolo snapshot non prova valore incrementale.
- Plusvalenza attesa partecipa all'obiettivo del solver tramite valore marginale del budget. Non è una correzione del PDK; non va confrontata come se lo fosse.
- `injury_list_size` è generata in `build_feature_matrix`, ma non figura in `FEATURE_COLS`; non è quindi un predittore diretto del regressore corrente. Questo aggregato non sostituisce feature individuali di disponibilità.

Non è possibile chiamare “ridondanti” statistiche correlate solo dal codice: servono ablation appaiate. Lag rolling e lag individuali si sovrappongono in parte, ma l'ablation salvata li valuta come famiglia; le feature opp-rating e DvP hanno granularità/fonte diverse, ma il contributo incrementale DvP non è stato misurato storicamente.

## 4. Evidenze quantitative già disponibili

Questa sezione riporta risultati di report salvati, non nuovi esperimenti. Gli artefatti elencati sono riproducibili, ma i periodi già analizzati non vanno trattati come holdout intatti per nuove selezioni.

| Domanda | Evidenza salvata | Lettura corretta |
|---|---|---|
| I lag recenti aggiungono informazione? | `dunkest_predictive_model_feature_enrichment_20261014_v1.md`: su 57.682 righe OOF, expanded lags vs adapter: MAE 7,5570 vs 7,5796; RMSE 9,8192 vs 9,8783; differenza MAE appaiata per data −0,02258, IC95% [−0,03270; −0,01239]. | Evidenza positiva di feature family nei fold 2022/23–2024/25; già integrata nel codice live, non nuovo intervento da promuovere.
| L'exact production trainer supera last-10? | Stesso report: MAE 7,5573 vs 7,7756 e RMSE 9,8230 vs 10,1316 su 57.682 righe. PDK effettivo ≥30: MAE 14,1802 vs 13,7098 (regressione). | Miglioramento generale, debolezza tail persistente; i target `actual ≥30` sono diagnostici retrospettivi, non un filtro ex ante.
| Serve correggere la coda alta? | Nested tail report `dunkest_production_tail_blend_nested_20261014_v1.md`: blend MAE 7,5477 vs produzione 7,5573, differenza piccola; MAE ≥30 14,1409 vs 14,1802, comunque peggiore di last-10 13,7098. Il peso selezionato cambia tra outer fold. | Miglioramento piccolo non sufficiente a promuovere un altro componente; non aumentare globalmente le proiezioni alte.
| La stagione corrente migliora il rate? | `dunkest_current_season_rate_blend_20261016_v1.md`: su 49.455 righe dev con actual minutes fissati, prior strength 12 ha MAE 6,3759 vs current-only 6,5774. | Diagnostica rate-only con esposizione/minuti reali, non end-to-end PDK; il valore è già stato incorporato e va monitorato, non ritunato sullo stesso campione.
| Quanto vale history PDK ufficiale rispetto al proxy? | `dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason.md`: 30.971 righe in validation seasons 2021/22–2024/25; ΔMAE official-minus-proxy −0,0031; bootstrap 95% [−0,0079; +0,0014]. | Nessuna prova conclusiva di valore incrementale; restano utile come target ufficiale, ma non si giustifica un ulteriore peso.
| È meglio un HGB minuti? | `dunkest_minutes_hgb_recency_walk_forward_20261024_v1.md`: HGB iniziale 2025/26 MAE 4,7948 vs prev5 4,9935 minuti; con recency weighting 4,8037. Bias HGB +0,2571 vs prev5 +0,0947; zero-minute cases sono deboli. | Migliora l'errore minuti nel test salvato ma non è una previsione end-to-end live; rimane shadow.
| Il modello shadow migliora PDK se usato per rescaling? | `dunkest_role_rotation_and_minutes_integration_20261014_v1.md`: rescaling HGB verso rapporto minuti peggiora PDK da MAE 7,5721 a 7,5816 già a peso 10%, fino a 7,7646 a pieno peso. | Evidenza contro l'integrazione semplice minuti×rate; non applicarla senza un nuovo confronto coerente.
| Cosa accade al tail nel test 2025/26 salvato? | `dunkest_pdk_high_score_error_diagnostic_20261026.md`: RF storico MAE 7,577 vs last-10 7,789 totale; effettivo ≥30 MAE 14,265 vs 13,771; per fascia RF prevista ≥30 bias medio circa +0,03 e recall outcome ≥30 29,2% vs 33,9%. | RF sperimentale non è il modello operativo; non mostra bias uniforme fra le previsioni RF alte, ma cattura meno outcome alti. Il holdout è già esaminato e non può essere riusato per selezionare parametri.

## 5. Difetti confermati, ipotesi e dati assenti

### Difetti/limiti verificati

1. **Nessuna prova live 2026/27 eleggibile:** GW3 contiene 148 candidati senza ID Dunkest e 2 chiavi feature ambigue, ed è senza archive seal/outcome riconciliato. Il validator è stato aggiornato nell'audit precedente per accettare soltanto fallback no-history espliciti; questo non sana il run né gli ID mancanti.
2. **HGB minuti non è output operativo:** i log `expected_min_model_shadow` sono utili per raccolta e confronto, ma il solver li rimuove; chi consulta solo il valore shadow potrebbe attribuirgli erroneamente impatto sul roster.
3. **DvP non è storicamente validabile:** 6 snapshot 2026/27, non una serie storica pre-lock; i valori variano fra acquisizioni. La correzione è attiva ma non OOS-calibrata.
4. **Il holdout storico 2025/26 è già stato consultato:** i risultati sono evidenza esplorativa consolidata, non una riserva intatta per tuning.
5. **Disponibilità/infortuni e mercato non hanno storia pre-lock pluristagione:** mancano prezzi, ruolo, lineup, assenze e roster point-in-time per un backtest esatto di optimizer o predictor runtime.
6. **Outcome coach esatti incompleti:** esistono metriche di vittoria/margine team, ma manca la combinazione storica affidabile di coach PDK ufficiale e quotazioni dei due coach alla stessa partita.

### Ipotesi ancora da verificare

- Feature della rotazione/ruolo possono aggiungere più sui giocatori con variazione di minuti recente che sulla popolazione totale; gli studi esistenti mostrano vantaggi di coorte piccoli/non uniformi e non giustificano un peso specialistico fisso.
- Cambi di squadra e assenze dei compagni possono migliorare minuti/rate se si archiviano transazioni, rotazioni, infortuni e status al cutoff; gli attuali flag team-change da log non sono un feed transazioni indipendente.
- DvP può aggiungere informazione ai contesti opp-rating già usati, ma il segnale potrebbe essere ridondante e le sue finestre sovrapposte; mancano snap pre-lock storici per misurarlo.
- Un modello two-stage presenza × minuti condizionati × produzione/min può migliorare le distribuzioni, ma oggi mancano previsioni/OOS matched della pipeline operativa con label zero/DNP complete per stimarne il beneficio netto.

## 6. Opportunità ordinate per valore e fattibilità

| Priorità | Analisi/intervento candidato | Dati realmente disponibili | Valore atteso | Costo | Affidabilità / rischio leakage | Decisione |
|---:|---|---|---|---|---|---|
| 1 | Rendere integro il ciclo prospettico: copertura ID Dunkest del pool candidati, runtime join univoco, sigillo/reviewer, outcome ufficiali separati. | Run 2026/27 con snapshots e manifest; caso GW3 diagnostico; codice writer/reviewer/outcome. | **Molto alto** perché abilita l'unica verifica diretta dell'attuale sistema operativo e dei cambi di ruolo/DvP. | Medio; nessun training. | Alta se ID/outcome ufficiali e cutoff vengono verificati; rischio principale è accettare proxy o dati post-lock. | **Prima priorità operativa**; raccogliere mediante run normali, non sintetizzare.
| 2 | Diagnosi/appaiamento dei residui PDK per salto di minuti, trend recenti, storia, cambio squadra e score-band su OOF storico già salvato; testare famiglie singole solo sul development ancora ammesso. | 112k training table, OOF/prediction artifacts e feature pre-target. | Alto per identificare se i miss sono minuti o rate; già vi sono segnali di errore tail e coorti rotation. | Basso–medio; analisi offline. | Media-alta con date-cluster bootstrap e feature as-of; ruoli/infortuni storici incompleti limitano interpretazione causale. | **Eseguire come prossimo esperimento quantitativo**, senza riusare 2025/26 per scegliere parametri.
| 3 | Valutare DvP incrementale e roster/coach con stessi forecast, input pre-lock e target ufficiali. | DvP completo solo per 6 catture iniziali; coach/player live snapshots parziali. | Potenzialmente alto ma incerto. | Medio-alto, richiede stagioni/snapshot. | Attualmente bassa per OOS: nessuna storia pre-lock DvP/coach prices. | **Dopo raccolta minima**, lasciare i componenti in produzione/shadow e non ritunare ora.
| 4 | Priors rookies/low-history per coorti ruolo/CR e incertezza. | 264 target rookie official 2020–25, rookie college file, prior OOF report. | Medio-alto per inizio stagione; numerosità modesta per sottogruppi. | Basso–medio. | Media; mapping draft/ID e composizione ruolo sono fattori sensibili. | Prima fare audit di coverage e walk-forward per classe, non ampliare il prior.
| 5 | Validare tre rose, costo opportunità, coach, plusvalenza e transfer malus su actual roster. | Solver/test sintetici e report proxy storici; dati CR storici same-lock assenti. | Molto alto per prodotto, ma non misurabile fedelmente oggi. | Alto. | Bassa finché si usano prezzi/roster ricostruiti o proxy. | Aspettare bundle prospettici eleggibili; separare qualità predittore e policy solver.

## 7. Piano sperimentale riproducibile

1. **Congelare il contratto di valutazione.** Per ogni forecast naturale, conservare tutti i candidati e l'universo ammesso, ID Dunkest/NBA player/game, cutoff, modello/config, feature/runtime/market/injury/fixture con timestamp/hash; reviewer deve marcare eleggibilità e motivi. Dopo il lock raccogliere outcome ufficiali senza modificare il forecast. Ambigui, nulli, DNP, zero minuti, rinviati e risultati mancanti devono restare stati distinti.
2. **Baseline storica development-only.** Usare espanding-origin per date/stagioni con lo stesso campione per candidato e baseline last-5/last-10/production adapter. I report storici 2022/23–2024/25 sono stati già usati per selezione; ogni nuovo ablation va dichiarato esplorativo e le decisioni definitive vanno riservate a un periodo prospettico futuro, non alla GW1 congelata o al 2025/26 già consultato.
3. **Feature family una alla volta.** (a) forma recente/lag PDK; (b) minuti e ruolo; (c) team-change/availability, solo se ex ante osservati; (d) matchup/DvP; (e) combinazioni solo dei blocchi che migliorano senza regressioni. Fitting, imputazione, selezione e calibrazione devono stare nel training fold; validation interno decide eventuali parametri, outer holdout misura una volta.
4. **Metriche appaiate.** MAE/RMSE/bias complessivi e per fasce di PDK previsto; recall/precision e calibrazione della probabilità di superare soglie predefinite (≥25, ≥30) con soglia ex ante; coorti per storico e, quando davvero point-in-time, rookie/ruolo/cambio squadra/availability. Bootstrap per data o partita. Le coorti `actual PDK ≥30` servono solo a diagnosticare, non a selezionare input.
5. **Separare minuti e scoring.** Per output shadow minutes confrontare MAE/RMSE/bias su tutti gli esiti verificati, inclusi zero/DNP con stati distinti; per PDK usare il predictor operativo senza sostituire i minuti a posteriori. Una ricalibrazione rate/minutes va ammessa solo se il PDK finale migliora sulle stesse partite.
6. **Valutare le rose soltanto dopo il predictor.** Riprodurre esattamente listino, ruoli, coach CR, disponibilità, budget, regole e transfer malus al cutoff. Confrontare tre rose/alternativa sullo stesso universo; non interpretare differenze di selezione come guadagno senza actual roster outcomes.

### Metriche e gate di accettazione

- Predictor PDK: MAE, RMSE e bias; tail score-band definita dal **previsto**; recall/precision outcome alti; coorti prioritarie con numerosità; differenza appaiata e IC bootstrap per giornata/data.
- Minuti: MAE/RMSE/bias, calibrazione degli zero/DNP e fasce di minuti, separando presenti con minuti positivi, zero verificati e non disponibili/non riconciliati.
- Rose: PDK ufficiale realizzato della rosa, contributi slot/capitano/sesto/bench/coach e malus, vincoli validati; denominatore = giornate con universo/costi/outcome completi.
- Promuovere solo quando il test indipendente è cronologico e comune, l'intervallo delle differenze e la variabilità tra giornate supportano il valore pratico, senza regressioni gravi nelle coorti prioritarie. Non fissare qui una soglia numerica universale né scegliere parametri sul test finale.

## 8. Raccomandazioni, ordinate

1. **Completare la raccolta pre-lock e i collegamenti ufficiali.** È la prima azione consigliata: risolve il principale blocco probatorio e permette di misurare il modello live 2026/27. Non generare un run artificiale e non recuperare gli ID del GW3 a posteriori.
2. **Eseguire un'unica diagnosi storica mirata delle code e dei salti di minuti/ruolo**, sugli OOF development già salvati e feature realmente pre-target; focalizzarsi su previsioni alte e giocatori con `min_last_vs_prev5`, team-change/history. Non promuovere un nuovo modello finché un confronto end-to-end PDK non è condiviso.
3. **Tenere shadow DvP/minuti e modelli coach separati finché non si accumulano snapshot pre-cutoff e outcome.** La semplice copertura o plausibilità del matchup non dimostra incremento predittivo.

## 9. Distinzione fra risultati, ipotesi e impossibilità

- **Dimostrato da confronti salvati:** i lag expanded migliorano errori medi storici; l'HGB migliora minuti contro prev5 nel dataset storico, ma la sua integrazione semplice ai PDK è dannosa; DvP/coach live non sono validati; il RF 2025/26 ha regressione sull'effettivo ≥30 e minore recall di coda ma non è il modello live.
- **Ipotesi:** feature disponibilità ex ante e cambi di ruolo possono aggiungere valore sostanziale; un modello di presenza/minuti/rate a più stadi potrebbe migliorare forecast distribuzionali; DvP può integrare opp-rating.
- **Non valutabile ora:** impatto prospettico del predictor live su GW 2026/27; valore di DvP in epoche passate; accuratezza DNP/infortuni storici; prezzi/plusvalenze e coach PDK al lock; Team-at-Rest storico completo; rendimento reale delle tre rose rispetto alla policy optimizer.

## 10. Stato del repository e verifiche svolte

La working tree era già modificata all'inizio; il report è l'unico nuovo file di questa attività. Ho lasciato intatti tutti gli altri file e dati.

Comandi/letture effettivamente eseguiti in questa fase: `git status --short`, `rg --files ...`, `graphify query ... --budget 2200`, `rg -n` sui punti di integrazione, letture `sed`/`cat` di `train.py`, `builder.py`, `predictor.py`, `pipeline/predict.py`, `pipeline/optimize.py`, `milp.py`, `artifacts.py`, `defense_vs_position.py` e dei report quantitativi indicati sopra; piccolo parsing AST locale per contare i nomi in `FEATURE_COLS` (**68**). Nessuna suite di test è stata eseguita perché non è stato modificato codice; nessun dato o report preesistente è stato riscritto.
