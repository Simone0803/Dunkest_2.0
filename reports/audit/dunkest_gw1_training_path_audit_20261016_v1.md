# Audit mirato del percorso di training GW1 Dunkest — 2026-10-16

## Esito

**Aggiornamento 2026-10-16:** il contratto delle quattro feature PDK esaminate è stato uniformato nel codice e verificato con test mirati e confronto dell’adapter sul dataset locale. Il blocco di coerenza limitato a queste feature è risolto; non è stato eseguito training e questo esito non certifica accuratezza predittiva, prestazioni OOS o correttezza end-to-end GW1. Vedi “Implementazione del contratto comune” in fondo.

## Percorso e target — verifica statica

1. Il comando `season-opener` carica `config/season_opener.yaml`, che imposta `training_target: target_pdk_official` e `opening_multiseason_training: true`.
2. `run_train` per GW1 carica i log della stagione precedente, applica l’overlay ufficiale ai log e costruisce le feature per l’inferenza. Per il trainer supervisionato, con `current_features=None` a GW1, invoca invece `train_multiseason_models`.
3. Il trainer multistagione legge `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet`, adatta le righe certificate e passa a `train_models` `target_column="target_pdk_official"`.
4. L’adapter crea `target_pdk_official` dal campo `target_pdk` del dataset V3. Gli audit di build V2/V3 definiscono quel campo come PDK Dunkest ufficiale valido; per la V3 le righe aggiunte hanno flag `gameValidForDunkest=True` e match player/data/opponente NBA verificato. Il codice non rimpiazza questa etichetta con il proxy durante l’adattamento o la chiamata del trainer.
5. Nell’adapter GW1 `expected_pdk_minutes_model` vale zero; in `train_models` il target del regressore è `target_pdk_official - expected_pdk_minutes_model`, quindi conserva il valore ufficiale.

Il percorso di inferenza costruito separatamente da `run_train` usa la funzione `_pdk_feature_series`, che preferisce la storia ufficiale ma può completarla con PDK proxy quando l’etichetta storica ufficiale non è disponibile. Questo riguarda le feature storiche d’inferenza, non il target supervisionato del dataset GW1. La differenza di provenienza delle feature resta da monitorare e non è stata rivalutata in questo audit.

## Dataset e feature — controlli read-only eseguiti

È stato letto il dataset locale attraverso lo stesso adapter usato dal trainer, includendo il file locale di minuti storici che il trainer carica quando presente. Non sono stati scritti artefatti nel dataset e non è stato addestrato alcun modello.

- Dataset sorgente: **112.178** righe, stagioni 2020/21–2025/26.
- Righe dopo l’adapter GW1: **93.766**, stagioni 2020/21–2024/25; il 2025/26 è escluso dal training.
- `target_pdk_official`: **93.766 valori finiti**, sopra la soglia di 1.000.
- Whitelist in `FEATURE_COLS`: **68** colonne; **56** hanno almeno un valore finito dopo l’adattamento e **12** sono assenti o completamente vuote.
- Le 12 colonne escluse sono: `pdk_mean_15`, `min_mean_10`, `fta_per36_5`, `fg3_pct_5`, `ft_pct_5`, `three_point_bonus_mean_5`, `pdk_category_bonus_mean_5`, `opp_pts_allowed_mean_5`, `opp_plus_minus_mean_5`, `opp_def_rating_mean_5`, `opp_pace_mean_5`, `opp_dreb_rate_mean_5`.
- Il codice del trainer elimina le colonne assenti o senza valori finiti; richiede almeno una feature utilizzabile. Per le colonne rimaste, sostituisce i mancanti con mediane calcolate sul training set (e zero solo quando la mediana non esiste). Le mediane dei fold OOF vengono calcolate sul rispettivo train split.
- Un controllo dati senza fit ha ricostruito i tre cutoff OOF cronologici: train di **37.008**, **55.249** e **74.447** righe, tutti con **56 feature** che contengono almeno un valore finito.

Non esiste nel codice un contratto che dichiari tutte le 68 feature obbligatorie. La disponibilità di 56 feature è stata verificata; non è stato verificato che sia sufficiente per l’accuratezza desiderata.

## Leakage temporale — evidenza statica e audit riusato

- Il builder V3 ricostruisce lag e rolling PDK ordinando i target ufficiali e applicando `shift(1)` prima delle aggregazioni.
- Le feature NBA V3 arrivano da un join as-of con `direction="backward"` e `allow_exact_matches=False`; l’audit di build riporta zero intervalli di riposo nulli/non positivi e zero duplicati player/game.
- L’adapter esclude il 2025/26 e rifiuta righe oltre il cutoff 2025-07-01; controlla chiavi duplicate e target non finiti.
- Le feature di target sono escluse dalla whitelist e `validate_prematch_features` vieta esplicitamente target e risultati post-partita come predittori.
- I fold OOF del trainer separano per data: il train usa date strettamente precedenti al primo giorno di validazione; preprocessing dei fold calcolato sul solo train.
- L’audit dataset preesistente riporta zero mismatch dei lag storici rispetto alla V2 e zero NBA history allo stesso giorno o successiva al target.

Queste evidenze sostengono l’assenza di leakage evidente nel dataset supervisionato; non equivalgono a un test indipendente di ogni riga né certificano la temporaneità dei dati usati nella futura inferenza GW1.

## Test eseguiti

Comando:

```text
PYTHONPATH=src .venv/bin/pytest -q tests/test_multiseason_training.py tests/test_official_pdk_labels.py tests/test_official_pdk_training_target_integration.py tests/test_temporal_validation.py tests/test_config_options.py
```

Esito: **31 passed**. I test coprono adapter/cutoff multistagione, target ufficiale, gestione esplicita del proxy, guardie temporali e configurazione GW1. `run_train` e il fit multistagione non sono stati invocati.

## Limiti residui e decisione

- Le 12 feature senza valori sono rimosse dal trainer; questa è una degradazione nota del set di input rispetto alla whitelist, non un errore di target. Non è stato stimato il suo impatto predittivo.
- Il ramo di inferenza può usare feature storiche proxy come fallback quando manca PDK ufficiale; la coerenza target/feature non è certificata da questa verifica del dataset supervisionato.
- Nessuna run end-to-end, metrica OOS, validazione di accuratezza, scraping o ricerca di iperparametri è stata eseguita.
- Lo stato Git iniziale conteneva già modifiche in `predictor.py`, `test_official_pdk_labels.py` e il report di completamento V2; questo audit non le ha alterate. L’unico nuovo file è questo report.

La decisione originale di procedere era basata sui soli controlli del percorso e del target; è stata superata dalla successiva analisi di coerenza riportata sotto.

## Audit aggiuntivo pre-implementazione: coerenza delle feature storiche PDK — 2026-10-16

Questa sezione aggiorna la decisione precedente, limitatamente alla coerenza training/inferenza delle feature PDK nel percorso GW1. Il controllo ha letto codice, report e file Parquet locali; non ha chiamato `run_train`, fit, scraping o esperimenti. Non sono stati modificati codice, pesi, target, dataset o snapshot. I test sono elencati sotto.

### Provenienza, disponibilità e comportamento

Nel dataset V3 il campo sorgente `target_pdk` è il punteggio PDK ufficiale per le sole partite Dunkest valide e abbinate univocamente. Le feature storiche vengono ricostruite in ordine cronologico da quei target; rolling e lag sono precedenti alla riga obiettivo. Nell’inferenza, `PDK` è invece il punteggio proxy calcolato dai box score NBA (`pdk_from_boxscore_row`). `_pdk_feature_series` usa l’etichetta ufficiale quando presente, e la completa con il proxy quando manca. Il fallback non cambia il target supervisionato, ma cambia la popolazione di valori che alimenta le feature.

| Feature PDK | Training multistagione | Inferenza GW1 | Valutazione |
|---|---|---|---|
| `pdk_mean_3`, `pdk_mean_5`, `pdk_mean_10`; `lag1_pdk`…`lag5_pdk` | Rolling/lag dai precedenti target ufficiali V3, attraverso i confini tra stagioni | Medesime finestre/lag, usando ufficiali più proxy per righe senza ufficiale; `shift(1)` | Formula e temporalità sostanzialmente allineate; provenienza non allineata quando c’è fallback. |
| `pdk_std_5`, `pdk_median_5` | Deviazione standard dei precedenti 5 target; mediana dei 5 lag disponibili | Statistiche sui precedenti 5 valori della serie ufficiale-completata con proxy | Formula allineata; stessa differenza di provenienza. La mediana ignora mancanti in entrambi i percorsi. |
| `pdk_trend_3v10` | `prev3_pdk_mean - prev10_pdk_mean` | `pdk_mean_3 - pdk_mean_10` | Definizione allineata; eredita la differenza di provenienza. |
| `pdk_season_mean` | Adapter assegna direttamente `prev10_pdk_mean` | Media espandente dei valori storici disponibili, shiftata per escludere la partita corrente | **Incoerenza dimostrata:** la feature chiamata “stagionale” è una media mobile 10 nel training e una media della stagione sorgente in inferenza. |
| `pdk_per_min_season` | `prev5_pdk_mean / prev5_nba_min_mean` | Somma PDK storici divisa per somma minuti storici positivi, usando valori ufficiali e proxy | **Incoerenza dimostrata:** rapporto su finestre di 5 nel training contro rapporto cumulativo pesato per minuti in inferenza; differisce anche la provenienza. |
| `player_opp_pdk_per_min` | Copia di `pdk_per_min_season`, quindi rapporto PDK/minuti della finestra recente; non dipende dall’avversario | Tasso specifico contro l’avversario con shrinkage di 120 minuti verso il tasso base; il valore per la fixture GW1 è aggiornato con l’avversario previsto | **Incoerenza dimostrata:** la semantica cambia da tasso recente generale a tasso head-to-head shrunk. |
| `player_opp_games` | Costante `0.0` su tutte le righe adattate | Numero di precedenti partite contro l’avversario quando le partite/minuti sono disponibili | **Incoerenza dimostrata:** feature costante in training, potenzialmente positiva in inferenza. |
| `history_games_before_target` | Conteggio cumulativo di righe ufficiali precedenti nel V3 attraverso le stagioni incluse | Conteggio di precedenti etichette ufficiali nel log caricato; se manca del tutto la colonna ufficiale, il codice conta i PDK della serie proxy | **Possibile differenza di distribuzione:** nell’avvio GW1 l’inferenza dispone del log della sola stagione precedente, mentre il training conta la storia V3 su più stagioni. Il conteggio esclude proxy se la colonna ufficiale esiste. |
| `pdk_mean_15` | Assente nel dataset adattato e quindi priva di valori finiti; il trainer la elimina dalla matrice effettiva | Calcolabile dal builder se la finestra 15 è richiesta | Nessuna feature effettiva con cui confrontare nel modello GW1: la whitelist di inferenza non la rende automaticamente una feature addestrata. |

Le feature PDK in whitelist sono quindi le 17 colonne elencate nella tabella (contando i cinque lag singolarmente). Le altre feature storiche `lag*_nba_*`, statistiche NBA e minuti hanno sorgenti NBA e non sono incluse nell’inventario PDK; l’audit precedente riporta controlli temporali per quelle sorgenti.

### Mancanti, fallback e misura locale

È stato caricato in sola lettura `data/processed/player_game_logs_2025-26.parquet` e applicato l’overlay locale V4 tramite `attach_official_pdk_labels`; nessun aggiornamento remoto o scraping. Il log contiene **24.100** righe: **18.141** con PDK ufficiale finito, tutte **24.100** con PDK proxy finito, e **5.959** con ufficiale mancante ma proxy disponibile. Nell’overlay, **5.369** righe sono esplicitamente `gameValidForDunkest=False`; le altre mancanti derivano da righe non abbinate/chiavi non coperte nel log corrente. L’overlay ha 24.424 righe e il join ha associato 24.052 delle 24.100 righe NBA; il loader ha emesso il warning per 48 righe non abbinate.

Per le **18.141** righe in cui entrambi i punteggi esistono, `PDK_proxy - PDK_ufficiale` ha media **−0,514**, mediana **−0,200** e MAE **0,530** punti. Sono descrittive delle etichette di una stagione locale, non metriche di accuratezza né prova dell’impatto sulle feature o sul modello.

La sostituzione ufficiale→proxy è esplicita e utile per mantenere una storia di performance NBA dove l’ufficiale manca; non è automaticamente un errore. È però una popolazione più ampia dei soli incontri validi Dunkest usati dal training. In particolare, includere proxy per incontri marcati non validi può mescolare punteggi proxy non certificati nella storia PDK. I dati locali non dimostrano che ciò migliori o peggiori la previsione.

### Temporalità e classificazione delle evidenze

**Problemi dimostrati nel contratto delle feature:** `pdk_season_mean`, `pdk_per_min_season`, `player_opp_pdk_per_min` e `player_opp_games` hanno definizioni diverse fra adapter di training e builder di inferenza. `pdk_mean_15` è prodotto solo dall’inferenza ma viene rimosso dal training come feature tutta mancante. Le trasformazioni di rolling/lag e il trend sono past-only in entrambi i percorsi esaminati; l’inferenza usa shift/espansione e filtra la fixture futura con data strettamente precedente. Non emerge leakage temporale evidente nelle feature PDK esaminate.

**Rischi plausibili, non quantificati sul modello:** i proxy mancanti ufficiali alimentano lag/rolling/tassi d’inferenza, mentre il V3 usa solo target ufficiali; il proxy differisce dall’ufficiale anche quando entrambi esistono. `history_games_before_target` può avere scale diverse per la diversa profondità di storia disponibile. La differenza nel feature contract può influire sull’inferenza, ma senza fit e confronto out-of-sample non se ne può stabilire direzione o entità.

**Non verificato:** valore/impatto delle differenze su predizioni GW1, decisione corretta per i 5.369 incontri non validi (escluderli o mantenerli come proxy), copertura ed esattezza dell’overlay per ogni fixture futura, e distribuzioni condizionate per giocatore/ruolo. Non sono state analizzate snapshot prospettiche né usate per tuning.

### Test e decisione aggiornata

Eseguito il comando mirato:

```text
PYTHONPATH=src .venv/bin/pytest -q tests/test_player_stat_features.py tests/test_multiseason_training.py
```

Esito: **17 passed**. I test esistenti verificano feature passate, priorità dell’ufficiale con fallback proxy e mapping multistagione; non certificano la parità semantica fra tutte le feature elencate. Non sono stati aggiunti test perché questa verifica non introduce modifiche al codice e il disallineamento è direttamente dimostrato dalle trasformazioni esistenti; test di parità sarebbero opportuni insieme alla correzione concordata del contratto.

**Decisione pre-implementazione:** le quattro incoerenze dimostrate (`pdk_season_mean`, `pdk_per_min_season`, `player_opp_pdk_per_min`, `player_opp_games`) bloccavano la raccomandazione di avviare il training. La sezione finale registra l’intervento che le ha uniformate. I fallback proxy delle altre feature restano separati da questo intervento. Nessuna conclusione sull’accuratezza predittiva è possibile da questo audit.

**Prossimo passo consigliato all’epoca:** definire un contratto unico e causale per queste quattro feature in training e inferenza, poi aggiungere test di parità mirati. L’implementazione di tale passo è registrata nella sezione successiva; il test prospettico GW1 resta isolato fino al cutoff già stabilito.

## Implementazione del contratto comune — 2026-10-16

### Definizioni adottate

Le due pipeline usano ora le stesse regole pure in `dunkest.features.pdk_history`:

- **Provenienza:** contribuisce solo `target_pdk_official` (training) o `PDK_OFFICIAL_VALID` (inferenza). `PDK` proxy non è usato per queste quattro feature. Se la colonna ufficiale è assente o nulla, il valore è mancante; il proxy continua a essere disponibile alle altre feature storiche che già lo prevedono.
- **Stagione selezionata:** per una riga target si usa la stagione target se esiste almeno uno score ufficiale precedente; all’apertura, si usa la stagione precedente più recente con almeno uno score ufficiale. Le statistiche non mescolano stagioni.
- **`pdk_season_mean`:** media aritmetica degli score PDK ufficiali finiti nella stagione selezionata; unità: punti PDK per partita ufficiale. Non richiede minuti.
- **`pdk_per_min_season`:** somma degli score PDK ufficiali / somma dei minuti NBA finiti e strettamente positivi, nella stagione selezionata; unità: punti PDK per minuto. Senza un denominatore positivo il valore è `NaN`.
- **`player_opp_pdk_per_min`:** stesso tasso base stagionale, con shrinkage di 120 minuti verso il tasso head-to-head nella stessa stagione: `(PDK_ufficiale_vs_opponente + 120 × tasso_base) / (minuti_vs_opponente + 120)`. Partite eleggibili: PDK ufficiale finito e minuti positivi. Se non ci sono partite contro l’avversario, usa il tasso base; se il tasso base non è disponibile, restituisce `NaN`.
- **`player_opp_games`:** conteggio delle partite head-to-head nella stagione selezionata con PDK ufficiale finito e minuti positivi. Avversario assente o nessun incontro eleggibile produce `0.0`.
- **Disponibilità temporale:** ciascun record è emesso prima di aggiungere target e minuti della partita corrente. I record sono ordinati per data e partita; l’adapter training rifiuta date duplicate dello stesso giocatore perché non esiste un ordinamento intraday verificabile. L’inferenza mantiene il controllo esistente sulle date duplicate e filtra la fixture pianificata con timestamp strettamente successivo allo storico.

### File modificati

- `src/dunkest/features/pdk_history.py` — nuovo accumulatore condiviso, formula, stagione e provenienza ufficiale-only.
- `src/dunkest/features/builder.py` — il percorso inferenza usa le definizioni comuni per le righe storiche, l’ultima riga e la fixture prevista.
- `src/dunkest/models/multiseason_training.py` — l’adapter ricostruisce le stesse quattro feature dai soli target ufficiali e dai minuti storici abbinati; il target supervisionato, pesi e cutoff restano invariati.
- `tests/test_pdk_history_contract.py` — test di parità cross-path, temporalità, unità/schema, minuti nulli/zero, assenza di storico e avversario senza storia.
- `tests/test_player_stat_features.py` — chiarisce che il proxy può restare nei rolling PDK generali, ma non nelle quattro feature coperte dal contratto.

### Verifiche eseguite

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_pdk_history_contract.py tests/test_player_stat_features.py tests/test_multiseason_training.py` — **21 passed**.
- Esecuzione read-only dell’adapter GW1 sul dataset V3 e sul file locale dei minuti; nessun fit: **93.766** righe con target ufficiale finito. Conteggi finiti: `pdk_season_mean` **92.902**, `pdk_per_min_season` **92.880**, `player_opp_pdk_per_min` **92.880**, `player_opp_games` **93.766**. I mancanti rimangono NaN, tranne il conteggio head-to-head che per definizione è zero quando non esiste storia eleggibile.
- `git diff --check` — esito pulito per i file tracciati; whitespace del report controllato separatamente e assente.
- Non sono stati eseguiti `run_train`, fit completi, scraping o esperimenti. Il test prospettico 2026/27 non è stato letto né usato.

### Decisione finale e limiti residui

Le quattro definizioni condividono ora la stessa funzione e un test applica training e inferenza agli stessi eventi sintetici, ottenendo parità numerica. Il dataset effettivo adattato fornisce valori finiti per le tre feature continue nella quasi totalità delle righe e zero esplicito per i conteggi senza matchup; nessun target viene modificato. Il blocco di coerenza relativo a queste quattro feature è quindi rimosso e il percorso può passare a una prima esecuzione controllata, se autorizzata dal piano operativo. L’accuratezza, le metriche OOS e la riuscita di un fit end-to-end restano da dimostrare. Le feature proxy diverse da queste quattro mantengono il comportamento precedente e non sono state riallineate in questo intervento.
