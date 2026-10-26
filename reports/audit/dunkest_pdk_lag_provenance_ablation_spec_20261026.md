# Dunkest 2.0 — provenienza temporale dei lag PDK e specifica di ablation

**Data:** 2026-10-26
**Ambito:** audit in sola lettura e preparazione dell’esperimento. Nessun training, scraping, forecast, modifica di modello/dati/archivi o test è stato eseguito. La working tree conteneva già modifiche; questo report è l’unico file creato da questa operazione.

## Esito

L’ablation salvata il 14 ottobre è riproducibile come confronto **24 feature adapter vs 50 feature arricchite** sui fold storici e sulle predizioni registrate. Non isola i sei lag PDK: li aggiunge insieme ad altre 20 feature. Le metriche favorevoli sono dunque evidenza sul blocco complessivo, non sul contributo marginale dei lag.

Il codice costruisce i lag in ordine di data ed esclude la partita target, ma gli artefatti storici non conservano il timestamp di acquisizione/pubblicazione del PDK di ciascuna riga sorgente. Questo certifica l’ordinamento **event-time** (`data partita < data target`), non che ogni etichetta fosse effettivamente disponibile al cutoff storico. Di conseguenza una nuova ablation sui fold storici può misurare un contributo condizionale alla pipeline di training ricostruita, ma non può essere presentata come confronto rigorosamente *as-of* o come prova OOS del predictor 2026/27.

Il confronto esatto con il predictor live è inoltre incompleto: il codice live dichiara 68 colonne candidate e usa ensemble/fit OOF; il test del 14 ottobre ricostruisce un adapter di 24 colonne e usa ExtraTrees e HGB separati. Non è una sostituzione uno-a-uno della produzione.

## Artefatti esatti dell’esperimento del 14 ottobre

Il codice e i risultati sono stati identificati tramite lettura dello script e JSON salvato. Gli hash SHA-256 verificati sono:

| Artefatto | Percorso | SHA-256 |
|---|---|---|
| Script ablation | `scripts/experiment_dunkest_pdk_lag_features_v2.py` | `80e72435310bcb6cc6b0ed582290d933a8ea8a0be7e025d9ef1388acf762d79e` |
| Audit JSON e metriche aggregate/fold | `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2.json` | `6df9ead0ce16463976b192f97af9ccf7000e0b415b63026e1f8bcc3578b5c7bb` |
| Predizioni per osservazione | `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2_predictions.csv` | `aaf15e05a88f17f97002dc5ee3afcdfa3341af7f9bd9fa5b83db59bdf48223f6` |
| Tabella training V3 | `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet` | `9f1cae2490822bc3617f96e35463473787fbfec016236f27a5c586f0cd9c72e5` |
| Helper feature/esperimento | `scripts/experiment_dunkest_minutes_rate_decomposition_v1.py` | `7daa99773baba265809cd98e53f755c424fd8eb1f7139c1a07dcc858a457f0e9` |
| Metadati acquisizione ufficiale stagione 2025/26 | `data/processed/official_dunkest_player_games_2025-26.meta.json` | `85c045efffb5787dcc0bcbe142c8a6c8644658a07ba67fc7130e234e4026c5e9` |

Il JSON riporta generazione `2026-10-14T19:53:50Z`, 93.753 righe nel source filtrato prima dei fold, nessun caricamento del holdout 2025/26 né del 2026/27, e fold di test 2022/23, 2023/24, 2024/25. Il campione comune delle metriche salvate è 57.682 righe. Il target è PDK di partita; i minuti e il PDK della partita target sono label e non input.

L’arm “adapter” ha 24 colonne. L’arm “expanded” ne ha 50, aggiungendo 26 colonne: sei PDK (`lag1_pdk`–`lag5_pdk`, `pdk_trend_3v10`), sei minuti/trend, dodici lag/media NBA di punti-rimbalzi-assist e due contatori di storico. Per ciascun fold lo script allena ExtraTrees o HGB con parametri fissati nel file, imputa le feature nei rispettivi pipeline e confronta le predizioni sulle stesse righe. I modelli sono learner singoli, non l’ensemble live.

### Risultati già archiviati — non nuovi risultati di questa analisi

| Modello e arm | n | MAE | RMSE | bias pred−osservato | MAE outcome ≥30 |
|---|---:|---:|---:|---:|---:|
| ExtraTrees, adapter 24 | 57.682 | 7,6042 | 9,9073 | −0,3700 | 14,4711 |
| ExtraTrees, expanded 50 | 57.682 | 7,5696 | 9,8458 | −0,1279 | 14,2108 |
| HGB, adapter 24 | 57.682 | 7,5810 | 9,8833 | −0,4366 | 14,5552 |
| HGB, expanded 50 | 57.682 | 7,5721 | 9,8304 | +0,0275 | 13,9971 |

Sono metriche già riportate negli artefatti; non sono state ricalcolate in questa fase. L’ablation del 14 ottobre non identifica l’effetto dei soli sei lag, né un effetto individuale per ciascun lag.

## Predictor live e comparabilità

`src/dunkest/models/predictor.py::FEATURE_COLS` contiene i sei campi, ma rappresenta colonne candidate: il set attivo dipende dalla disponibilità/validità al fit. Il predictor usa Ridge, Random Forest e Gradient Boosting con fit OOF e calibrazione residua per fascia; il trainer storico adatta i dati V3 a quel percorso, ma assegna `NaN` o proxy a campi non osservabili nello storico. In particolare, il test 14 ottobre definisce manualmente un adapter approssimato da 24 feature e non invoca la pipeline d’ensemble live.

Il source V3 ha 112.178 righe e 95 colonne; non contiene colonne con timestamp di acquisizione/osservazione/pubblicazione. Anche `official_dunkest_player_games_2025-26.parquet` (27.706 righe, 36 colonne) e `player_game_logs_2025-26_official_pdk_overlay_v4.parquet` non espongono timestamp per singola label. Il metadata API 2025/26 riporta un’acquisizione bulk (527 risposte, `2026-10-10T17:51:03.427802Z`), non il momento in cui ogni partita storica divenne disponibile. Non è quindi un audit temporale per ogni forecast storico.

**Conclusione di confrontabilità:** si può definire un’ablazione controllata sullo stesso dataset storico e con il trainer storico attuale, rimuovendo solo le sei colonne; non si può chiamarla replica esatta del forecast live 2026/27 né certificare l’accessibilità storica *as-of*. Per una replica più fedele serve che entrambi gli arm passino dalla stessa funzione di training/OOF/ensemble di produzione e che il generatore storico produca gli stessi input del live senza riempimenti non equivalenti. Anche allora resterebbe il limite dei timestamp storici.

## Provenienza dei sei lag

Il builder (`src/dunkest/features/builder.py::_pdk_feature_series`, `_history_features`) preferisce `PDK_OFFICIAL_VALID` e usa PDK proxy come fallback; `lagN_pdk` seleziona il valore N partite indietro della serie ordinata. `pdk_trend_3v10` è `pdk_mean_3 - pdk_mean_10`. `src/dunkest/features/pdk_history.py::pdk_history_features_for_rows` accumula solo record precedenti per data e rifiuta date duplicate. Questi controlli impediscono l’inclusione della partita target per data, ma non attestano il timestamp di acquisizione di ogni PDK storico. I lag non hanno un flag proprio che identifichi per singola riga se il valore sia ufficiale o proxy.

| Feature | Costruzione | Disponibilità storica pre-cutoff certificata | Solo dedotta dalla data | Disponibilità storica non verificabile |
|---|---|---|---|---|
| `lag1_pdk` | PDK della precedente partita in ordine data; official se presente, altrimenti proxy | **No** per i fold 2020/21–2024/25 | **Sì**, codice esclude la partita target e usa la riga precedente | **Sì**, manca acquisizione per ogni label e la quota proxy per valore non è attestata nel training V3 |
| `lag2_pdk` | Due partite prima | **No** per i fold storici | **Sì** | **Sì**, come sopra |
| `lag3_pdk` | Tre partite prima | **No** per i fold storici | **Sì** | **Sì**, come sopra |
| `lag4_pdk` | Quattro partite prima | **No** per i fold storici | **Sì** | **Sì**, come sopra |
| `lag5_pdk` | Cinque partite prima | **No** per i fold storici | **Sì** | **Sì**, come sopra |
| `pdk_trend_3v10` | Differenza tra media ultime 3 e ultime 10 della stessa serie PDK | **No** per i fold storici | **Sì**, se tutte le righe incluse sono precedenti per data | **Sì**, disponibilità effettiva di ciascun PDK e status ufficiale/proxy non tracciati a livello della feature |

### Evidenza timestamp disponibile per la stagione corrente

Sono presenti cinque snapshot round-level con timestamp: GW1 round 1 (68 righe, acquisito 23 ottobre 2026 15:28:53 UTC), GW1 round 2 (251 righe, 15:29:38 UTC), GW1 round 3 (22 righe, `observed_at_utc` 15:26:18 UTC; capture indicato 15:22:29 UTC), GW2 round 1 (272 righe, 25 ottobre 09:05:41 UTC) e GW2 round 2 (51 righe, 09:05:42 UTC). Contengono PDK, nome, squadra, giornata/round e `observed_at_utc`; alcuni hanno ID Dunkest. Sono catture correnti, non timestamp delle label storiche 2020–26. Possono certificare la disponibilità soltanto delle righe effettivamente riconciliate e solo per cutoff successivi al rispettivo `observed_at_utc`; non certificano la disponibilità dell’intero set di round né dei lag storici usati nell’ablation. Non è stato eseguito un join di copertura per giocatore-game, e quindi non si attribuisce a questi file una copertura più ampia di quella osservata.

## Procedura riproducibile proposta — non eseguita

L’esperimento minimo avrà due soli bracci e una sola differenza dichiarata:

1. **Baseline:** matrice delle feature del trainer live/storico scelto, incluse tutte le feature candidabili e attive al fold.
2. **Ablation:** stessa matrice meno esattamente `lag1_pdk`, `lag2_pdk`, `lag3_pdk`, `lag4_pdk`, `lag5_pdk`, `pdk_trend_3v10`.

Per renderlo ripetibile:

- Prima dell’esecuzione fissare hash di sorgente, dati, configurazione, versione librerie, target e definizione di `gameValidForDunkest`; conservare gli artefatti di predizione separati per braccio. Rifiutare output già esistenti invece di sovrascriverli.
- Usare solo righe con target PDK ufficiale valido e chiave giocatore-partita univoca; fissare **una volta** il campione ammissibile, quindi usare esattamente le stesse chiavi in entrambi i bracci. Nessun filtro dipendente dal valore previsto/effettivo.
- Usare fold expanding chronologici predefiniti 2022/23, 2023/24, 2024/25 (come l’ablation esistente) solo come sviluppo, se lo schema del trainer live è ricostruibile; tenere ogni stagione test fuori dal fit di preprocessing, modelli, ensemble e calibrazione. Non usare il 2025/26 già consultato per selezionare una variante e non usare GW1 2026/27.
- Bloccare learner, iperparametri, versione del preprocessing e regole di imputation/encoding prima dell’esperimento. Non cercare parametri specifici dell’arm ablation. Fit dei trasformatori dentro ciascun fold; identico algoritmo per entrambi gli arm. Se il live ensemble usa pesi OOF, usare la medesima procedura OOF nei due bracci, senza tuning specifico; registrare pesi ottenuti e campione OOF. La sola differenza consentita è l’omissione dei sei lag.
- Salvare una riga di predizione per chiave stabile, braccio e fold, con feature mask e hash; controllare che l’insieme di chiavi e target combaci esattamente prima di calcolare metriche.
- Riportare MAE, RMSE e bias complessivi e per fold. Calcolare differenze appaiate per osservazione e IC 95% con bootstrap a cluster per data/partita, ricampionando i cluster con lo stesso indice per i due bracci. Se la dipendenza intra-giornata è rilevante, usare la giornata Dunkest solo dove il mapping è verificato; altrimenti usare data di partita NBA, dichiarando questa unità.
- Per calibrazione, riportare media prevista, media osservata, MAE/RMSE/bias per fasce definite ex ante dalla **predizione baseline** (per esempio decili fissati sul training fold, applicati al test), in modo che i due bracci siano confrontati negli stessi strati. Outcome `>=25` e `>=30` restano diagnosi retrospettive, non feature o soglie per decisione live. Riportare anche recall/copertura della coda solo come diagnostica secondaria, con denominatori espliciti.
- Non promuovere da soli risultati sui fold di sviluppo già consultati. Una decisione live richiede raccolta prospettica: bundle pre-lock versionati eleggibili secondo il reviewer corrente, target ufficiali poi riconciliati, campioni appaiati e holdout non utilizzato per selezione.

**Nota di implementabilità:** con gli artefatti correnti si può preparare e in futuro eseguire il confronto *event-date* sul trainer storico. Per soddisfare la richiesta forte di identico predictor live, occorre prima verificare che la funzione di fit live accetti direttamente la matrice storica adattata e che entrambe le braccia condividano il suo OOF ensemble. Se ciò non è vero, il risultato va etichettato come “ablation nel trainer storico/adattatore”, non “contributo dei lag al predictor live”. La provenienza per data rimarrà comunque non certificata sui fold storici finché mancano log timestampati per le singole osservazioni.

## Stato dell’archivio prospettico

L’inventario locale contiene **5** `archive_manifest.json`, tutti in GW1 2026/27: uno (`20261018T124836Z_e475d5d9`) ha `pre_lock_eligible=true` secondo il vecchio schema v1/`verified_fresh`; quattro riportano `incomplete_evidence`. Il bundle legacy eleggibile non contiene il contratto corrente di snapshot forecast individuale, feature runtime e shadow, e non è equivalente al formato versionato richiesto per la nuova valutazione. Non sono presenti `post_match_*.parquet` locali. Pertanto nessun bundle GW1 è utilizzabile qui per metriche performance: manca l’outcome ufficiale riconciliato, e il bundle è legacy rispetto al contratto corrente. Il run GW3 `20261025T101251Z_6d20853d` resta diagnostico/non eleggibile e non va usato per selezione o confronto.

## Criteri decisionali

**Accettare l’ipotesi che il blocco dei lag aiuti** solo se, sullo stesso identico campione e con il medesimo trainer, preprocessing, target, fold e procedura OOF, l’arm con lag riduce MAE e/o RMSE in modo stabile tra fold e con IC appaiato che esclude zero per una differenza di valore pratico; bias e fasce di PDK previsto non devono mostrare regressioni rilevanti. Stabilità per fold e coorti prioritarie conta più di un miglioramento pooled minimo. La soglia di rilevanza pratica va fissata prima di vedere i nuovi risultati, sulla variabilità osservata e sul valore decisionale.

**Respingere o non promuovere** se il guadagno non è riproducibile, dipende da un solo fold, aumenta errori/bias nelle fasce previste alte o nelle coorti importanti, oppure se campioni/feature non sono appaiati. Un IC che include zero non dimostra equivalenza: l’esito resta inconclusivo, soprattutto con pochi cluster.

**Per una validazione temporale certificata** serve inoltre una prova pre-cutoff della disponibilità delle feature: acquisizione timestampata per il PDK ufficiale di ogni lag utilizzato, mapping stabile player-game, cutoff del forecast e trasformazione riproducibile. Il solo `game_date` non basta. In alternativa, la raccolta prospettica deve registrare input/feature effettivamente usati prima del lock e outcome ufficiali aggiunti separatamente. I bundle legacy GW1 non soddisfano questo criterio per la valutazione performance corrente.

## Comandi e verifiche effettuati

- `git status --short` — ha mostrato modifiche preesistenti; nessuna è stata ripristinata.
- `shasum -a 256` sui sei artefatti elencati — hash registrati sopra.
- `python3` read-only con `pandas` per schema/righe/colonne timestamp della tabella training, overlay ufficiali e cinque snapshot round-level; nessuna scrittura.
- Lettura di `scripts/experiment_dunkest_pdk_lag_features_v2.py`, JSON/CSV dell’ablation, `src/dunkest/models/predictor.py`, `src/dunkest/models/multiseason_training.py`, `src/dunkest/features/builder.py`, `src/dunkest/features/pdk_history.py`, `src/dunkest/data/dunkest/official_pdk.py` e report di eleggibilità/persistenza.
- Inventario read-only dei manifest sotto `data/archives/pre_lock/`.

Nessun test era necessario, poiché non è stato modificato codice. `git diff --check` è eseguito dopo la scrittura del report. Nessun training, scraping, forecast, tuning, modifica degli archivi, commit o push.
