# HGB shadow e ibrido di produzione — audit di parità e valutabilità

**Data:** 2026-10-24  
**Ambito:** solo valutazione; nessuna modifica a predictor operativo, pesi, optimizer o PDK.

## Sintesi della conclusione

Il confronto storico appaiato tra HGB e ibrido effettivo di produzione **non è ricostruibile con gli archivi locali disponibili**. Il training set storico 2020/21–2025/26 contiene 23 delle 68 feature correnti del predictor; non conserva gli snapshot Dunkest as-of necessari per ricalcolare il ramo ibrido. Non ho sostituito le previsioni mancanti con una baseline.

La sola comparazione autentica già archiviata tra `expected_min` di produzione e `expected_min_model_shadow` è il forecast GW1 2026/27 del 18 ottobre 2026. È un singolo forecast origin, il manifest dichiara `pre_lock_eligible=false`, la copertura degli esiti è selettiva e non comprende alcuno zero verificato. I suoi numeri restano diagnostici, non costituiscono un confronto walk-forward certificato.

## Differenze tra il replay precedente e il predictor reale

| Aspetto | Predictor/runtime HGB shadow | Replay storico Task 12 | Conseguenza |
|---|---|---|---|
| Schema | `FEATURE_COLS` in `src/dunkest/models/predictor.py`: 68 colonne numeriche selezionate, delle quali il training sceglie quelle presenti e finite | `BASE_NUM` estese, lag NBA/PDK e rate aggiuntivi, più `opponentTeamCode` e `opponentTeamPosition` categoriche | Feature e matrice risultante non coincidono |
| Disponibilità negli archivi storici | Le feature sono costruite da `build_feature_matrix` a partire da log, schedule, matchup e transizioni disponibili | Il parquet `dunkest_pdk_game_training_2020-26_v3.parquet` contiene 23/68 colonne runtime; 45 feature attuali non sono conservate | Non si può alimentare fedelmente il modello runtime storico |
| Imputazione | `_fit_matrix`: conversione numerica, inf→NaN, mediane calcolate sul training, poi zero; colonne tutte mancanti rimosse prima del fit. In inferenza si riusano le mediane salvate e si completa con zero | `SimpleImputer(median, add_indicator=True)` per numeriche e `SimpleImputer(most_frequent)` + `OneHotEncoder` per categoriche | Anche su colonne comuni, la trasformazione differisce per missing indicators, encoding e gestione delle feature assenti |
| Estimatore | `HistGradientBoostingRegressor(max_iter=180, learning_rate=.06, max_leaf_nodes=31, l2_regularization=5, min_samples_leaf=40, random_state=settings.random_state)` | Stessi principali parametri HGB, ma `random_state=2026` fisso nel modello di ricerca | I parametri vicini non rendono equivalenti feature, preprocessing o fit |
| Target e range | Addestramento su `target_min.clip(0,60)` se ci sono almeno 200 label finite; predizione shadow ritagliata a `[0,48]` | Addestramento sul target minuti verificato senza lo stesso clipping pre-fit; output ritagliato a `[0,48]` | Cambia il problema di fit sui target estremi |
| Previsione ibrida | È una regola/pipeline separata: `_base_minutes`, ruolo e prior crediti/lineup, prior di mercato/rookie, competition cap, allocazione posizionale; quindi componenti PDK e probabilità di gioco | Il replay storico misura solo l’estimatore HGB e la baseline `prev5` | Non esiste nel replay una previsione ibrida storica autentica da appaiare |
| Costruzione temporale | `build_feature_matrix` calcola rolling/lag shiftati, schedule, matchup e team transitions. Runtime applica inoltre dati di roster, mercato e disponibilità correnti | `make_features` deriva ulteriori rate/usage da parquet storico V3; `validate_temporal_fold` controlla i confini temporali | I controlli temporali del replay non provano la disponibilità as-of dei campi Dunkest mancanti |

I nuovi test verificano che fit e inferenza del **preprocessing numerico runtime** producano la stessa matrice quando riusano le mediane apprese; verificano anche che il preprocessore storico del replay produca una matrice diversa sullo stesso campione sintetico. Questo accerta la differenza d’implementazione, non ricostruisce input storici assenti.

## Tre livelli di confronto, tenuti separati

### 1. HGB iniziale vs variante recency

Riutilizzo il walk-forward del precedente audit, senza riaddestrare o applicare la variante recency. Su 2025/26 (18.412 player-game) la differenza recency − HGB iniziale era MAE **+0,0089** (IC 95% appaiato per partita `[+0,0022, +0,0153]`) e RMSE **+0,0080**. La variante recency è respinta. È un confronto interno tra due replay HGB storici, non con il predictor operativo.

### 2. HGB vs baseline semplice ultimi cinque minuti

Sul sottoinsieme comune 2025/26 con `prev5` disponibile (18.348 righe, 1.043 partite), il replay HGB iniziale ha MAE **4,7948**, RMSE **6,2465**, bias **+0,2571**; `prev5` ha MAE **4,9935**, RMSE **6,5595**, bias **+0,0947**. IC 95% bootstrap per partita di HGB − prev5: MAE `[-0,2324, -0,1656]`, RMSE `[-0,3603, -0,2683]`, bias `[+0,1148, +0,2080]`. Il vantaggio è sul campione condiviso rispetto a una baseline semplice; **non è evidenza di superiorità sull’ibrido di produzione**.

### 3. HGB shadow autentico vs minuti ibridi archiviati

Riutilizzo il confronto diagnostico del run `20261018T120440Z_88d2ef45`: sul sottoinsieme appaiato di 289 candidati in 16 partite, hybrid MAE/RMSE/bias = **7,2182 / 9,3209 / −5,3926**; HGB shadow = **5,2252 / 6,5678 / −0,7050**. Differenza HGB − hybrid: MAE **−1,9930**, RMSE **−2,7531**, bias **+4,6876**; IC 95% bootstrap per partita rispettivamente `[-2,4938, -1,5302]`, `[-3,4531, -2,0590]`, `[+4,1268, +5,2604]`.

Queste sono le due colonne autentiche salvate dallo stesso percorso di previsione, ma non autorizzano una conclusione: il manifest non certifica il pre-lock; solo 289/528 candidati sono appaiati; 233 non hanno esito e non sono trattati come zero; 6 candidati con log non hanno HGB; gli zero minuti verificati sono 0. Le 16 partite provengono da un unico forecast origin e non sono fold temporali indipendenti. Il bias HGB meno negativo non corregge la selezione degli esiti.

## Input e trasformazioni mancanti per il replay storico esatto

Gli archivi storici di training contengono log e lag utile al modello sperimentale, ma non gli input e i timestamp per partita che servono a ripetere il predictor completo: roster/ID e crediti Dunkest, ruolo e tag Lineups, status/infortuni con timestamp, avversari e fixture verificati, coach/matchup, mercato e storia di valore, prior rookie, disponibilità dei compagni, gruppo di rotazione e input per la competizione/allocation posizionale. Non è conservato un bundle delle feature runtime complete per ogni record storico né una previsione ibrida per ogni player-game delle stagioni 2022/23–2025/26.

Il run GW1 conserva `predictions.parquet`, `lineups.parquet`, mercato e coach, ma non un bundle certificabile delle feature runtime; il manifest non ha cutoff ufficiale e registra solo 17 input su 30 con timestamp d’acquisizione. Non è quindi possibile usare quel run per inferire parità di input o certificazione pre-lock. Il vecchio snapshot non viene modificato né ricertificato.

Perciò il PDK controfattuale resta **non valutabile**: sostituire i minuti shadow nell’equazione minuti × rate non riproduce il blend PDK, i cap/allocazione, il modello storico, i prior e la probabilità di partecipazione.

## Test e riproducibilità

Nuovo test: `tests/test_minutes_production_replay_equivalence.py`.

Test riutilizzati: `tests/test_minutes_recency_experiment.py` (ordine temporale, date delle feature storiche, target esclusi dalle feature) e `tests/test_minutes_comparison.py` (appaiamento, ordinamento, leakage temporale, duplicati, metriche e bootstrap riproducibili).

Comando:

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_minutes_production_replay_equivalence.py \
  tests/test_minutes_recency_experiment.py \
  tests/test_minutes_comparison.py
```

Esito: **12 passed**. `git diff --check`: superato. Nessuna modifica a codice di produzione; nessun training aggiuntivo, commit o push.

## Decisione operativa

Mantenere l’ibrido in produzione e HGB in shadow. Scartare la pesatura recency. I risultati HGB vs `prev5` non si trasferiscono al predictor corrente; l’unico confronto HGB-vs-hybrid autentico è un diagnostico incompleto e non certificato. Non c’è base per promuovere HGB né per valutare l’effetto PDK.

**Prossimo esperimento unico:** raccogliere più forecast origin pre-lock certificati che congelino feature runtime, ibrido e HGB sullo stesso pool stabile; riconciliare tutti i candidati inclusi zero/DNP verificati e poi eseguire il confronto appaiato per turno/fold con bootstrap per partita.
