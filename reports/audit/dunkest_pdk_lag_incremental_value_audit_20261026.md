# Dunkest 2.0 — verifica incrementale del valore dei lag PDK arricchiti

**Data:** 2026-10-26. **Ambito:** ispezione statica di codice, report OOF salvati e metadati archivio locali. Nessun modello, forecast, archivio o dato storico è stato modificato; nessun training, scraping o forecast è stato eseguito.

## Sintesi

I lag arricchiti **sono già presenti** nello schema del predictor live. L'esperimento storico disponibile non ha però isolato i singoli lag: ha confrontato 24 feature adapter con un gruppo da 50 che aggiungeva 26 variabili insieme, su 57.682 osservazioni in fold 2022/23–2024/25. L'effetto del gruppo è positivo in media, con differenze tra learner e stagioni; non si può attribuire il guadagno a `lag1_pdk`, agli altri lag, al trend o alle feature NBA aggiunte.

Il confronto non coincide con l'attuale predictor: il suo `FEATURE_COLS` contiene 68 nomi candidati e la matrice effettiva dipende dalle colonne finite del training. Non esistono predizioni salvate per la baseline live attuale e per una variante che differisca in un solo gruppo PDK, sugli stessi fold. Rispettando il vincolo di non addestrare, **non ho prodotto nuove metriche**.

La prima verifica minima raccomandata è un'ablation appaiata dell'attuale schema live contro lo stesso schema senza il blocco PDK lag `lag1_pdk`–`lag5_pdk` e `pdk_trend_3v10`, mantenendo ogni altra componente identica. È un esperimento di sviluppo, non una promozione: il 2025/26 è già stato consultato e il test finale dovrebbe restare su future giornate prospettiche certificate.

## Feature candidate e ciò che fu realmente confrontato

Il JSON salvato `reports/audit/dunkest_pdk_lag_feature_ablation_20261014_v2.json` definisce esattamente la differenza tra le due feature set. Le 26 colonne aggiunte rispetto all'adapter erano:

- **PDK recenti (6):** `lag1_pdk`, `lag2_pdk`, `lag3_pdk`, `lag4_pdk`, `lag5_pdk`, `pdk_trend_3v10`;
- **minuti e trend (6):** `lag1_nba_min`, `lag2_nba_min`, `lag3_nba_min`, `prev3_nba_min_mean`, `min_trend_3v5`, `min_last_vs_prev5`;
- **produzione recente (12):** lag 1–3 e media delle ultime 3 per punti, rimbalzi e assist;
- **copertura storico (2):** `history_games_before_target`, `nba_history_games_before_target`.

La lista esatta macchina è: i sei PDK qui sopra; `lag1_nba_min`, `lag2_nba_min`, `lag3_nba_min`, `prev3_nba_min_mean`, `min_trend_3v5`, `min_last_vs_prev5`; `lag1_nba_pts`, `lag2_nba_pts`, `lag3_nba_pts`, `prev3_nba_pts_mean`; analoghi quattro campi per rimbalzi e assist; i due conteggi di storico. Sono 26 colonne.

L'esperimento ha quindi dimostrato il valore del **blocco congiunto**, non dei singoli PDK lag. Non ha testato singolarmente finestre L1/L2/L3/L4/L5, il trend 3v10, oppure l'interazione di questi lag con il minutaggio.

### Metriche archiviate: report `dunkest_pdk_lag_feature_ablation_20261014_v2.md`

Stesso target, campione e fold: 57.682 righe ufficiali, fold espandenti 2022/23 (19.165), 2023/24 (18.927), 2024/25 (19.590). Target GW PDK e minuti erano label, non input.

| Learner / feature set | n | MAE | RMSE | Bias pred−obs | MAE actual ≥25 | MAE actual ≥30 | MAE history <5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ExtraTrees (`et12`), adapter 24 | 57.682 | 7,6042 | 9,9073 | −0,3700 | 12,4772 | 14,4711 | 5,2012 |
| ExtraTrees (`et12`), expanded 50 | 57.682 | 7,5696 | 9,8458 | −0,1279 | 12,2249 | 14,2108 | 5,1388 |
| HGB, adapter 24 | 57.682 | 7,5810 | 9,8833 | −0,4366 | 12,5434 | 14,5552 | 5,2469 |
| HGB, expanded 50 | 57.682 | 7,5721 | 9,8304 | +0,0275 | 12,0671 | 13,9971 | 5,1747 |

Le due famiglie learner migliorano pooled MAE/RMSE con le 26 colonne aggiunte. Per `et12` il MAE migliora in tutti e tre i fold (+? convenzione: expanded meno adapter: −0,0343 nel 2022/23, −0,0247 nel 2023/24, −0,0445 nel 2024/25). HGB migliora MAE nel 2022/23 di circa −0,0062 e nel 2024/25 di −0,0301, ma peggiora nel 2023/24 di +0,0101. Le metriche di coda ≥30 migliorano nei report per entrambi i learner, pur restando errori elevati e senza prova che i soli lag PDK ne siano responsabili.

Il report di arricchimento riporta anche per il blend ET/HGB 50/50 MAE 7,5796 → 7,5570 e RMSE 9,8783 → 9,8192; differenza MAE paired-by-date −0,02258, IC95% [−0,03270; −0,01239], 475 cluster data. È sempre il blocco di feature, non un confronto di singoli lag.

## Definizione e disponibilità temporale nel codice

- In `features/builder.py::_history_features`, i lag PDK sono letti da `pdk.iloc[-lag]`; in `_rolling_features` le serie target sono `shift(lag)` e i rolling sono `shift(1).rolling(...)`. `pdk_trend_3v10` è `pdk_mean_3 - pdk_mean_10`. Quindi il codice esclude la partita target per data.
- La serie usata per i lag/rolling PDK è `_pdk_feature_series`: preferisce `PDK_OFFICIAL_VALID` e fa fallback alla colonna PDK proxy dove il target ufficiale manca. Il conteggio `history_games_before_target` distingue il numero di label ufficiali dai `nba_history_games_before_target`; le singole feature lag non portano invece un flag per ogni lag che indichi se quel valore era ufficiale o proxy.
- In `models/multiseason_training.py`, il builder V3 ordina per data/giocatore e calcola i quattro PDK history summaries con `PdkHistoryAccumulator` prima di aggiungere l'outcome corrente. La preparazione impone unicità player/date e usa label ufficiali per tali riassunti; gli altri lag sono mappati da colonne precedenti del training table.
- `pdk_trend_3v10` è una trasformazione deterministica di `pdk_mean_3` e `pdk_mean_10`, entrambe già nel predictor live. Non porta nuova informazione osservata; può comunque cambiare la rappresentazione e l'induttive bias dei learner. La sua utilità va dimostrata, non presunta nulla.
- `predictor.py::FEATURE_COLS` corrente contiene tutti i sei PDK campi della proposta, insieme a minuti, rate, contesto opp e feature di ruolo. Il trainer usa solo colonne presenti e finite. Il numero 68 indica candidate columns, non garantisce che tutte siano attive in ogni fit.
- Nel live, gli input corrente vengono preparati usando log e snapshot che la pipeline aggiorna prima del forecast. Per le feature storiche il codice garantisce l'ordine per **data della partita**; gli artefatti storici non conservano sistematicamente un `observed_at_utc` per ciascun risultato Dunkest passato. Pertanto l'evidenza dimostra past-only per event date, ma non certifica, per ogni partita storica, il timestamp di effettiva acquisizione/pubblicazione del PDK. Il live overlay dei risultati di turno ha invece timestamp e gate pre-cutoff; non va confuso con il backfill storico.

### Ridondanza e candidati utili

- `pdk_trend_3v10` è matematicamente ridondante rispetto alle due medie già esistenti. È un buon test singolo a basso costo, ma l'esperimento originale non ne isola il valore.
- `lag1_pdk`–`lag5_pdk` si sovrappongono alle medie rolling 3/5/10 ma conservano forma/ordine degli ultimi risultati; la sovrapposizione non basta a dichiararli ridondanti. Per ogni record il loro valore può essere official o proxy; la copertura e la provenienza dei lag devono essere stratificate.
- `lag1_nba_min` e `min_last_vs_prev5` condividono informazione; `min_trend_3v5` e `prev3_nba_min_mean` sono anch'essi correlati. Non sono parte del blocco PDK proposto e devono restare invariati nell'ablation PDK.

## Comparabilità con il predictor live

Il confronto storico ha vantaggi: stesso campione appaiato, target ufficiale, fold cronologici espandenti, feature numeriche e nessun target-game PDK/minuti negli input. È utile come evidenza che un arricchimento lagged può aiutare alcuni learner.

Non è un confronto diretto con l'attuale predictor live perché:

1. la baseline del test era un adapter ricostruito con 24 colonne, non l'attuale schema operativo da 68 candidate columns;
2. la variante expanded usava 50 colonne, incluse feature NBA minuti/box e history counts, oltre ai PDK lag;
3. i learner usati nell'ablation (`et12` e HGB) non rappresentano da soli l'ensemble live Ridge/RF/GBR e i suoi pesi di proiezione OOF;
4. i 57.682 esempi sono le stagioni di sviluppo 2022/23–2024/25 già esaminate in più report. Non costituiscono un holdout intatto per una nuova scelta;
5. il holdout 2025/26 è stato già consultato e non deve essere riutilizzato per tuning;
6. il run GW3 `20261025T101251Z_6d20853d` non è eleggibile. Il suo snapshot incompleto non fornisce una replica del predictor con/out lag.

Il report exact production trainer su 57.682 righe, MAE 7,5573 contro last-10 7,7756 e RMSE 9,8230 contro 10,1316, conferma il comportamento del trainer storico con feature arricchite in quei fold; non misura l'incremento dei singoli sei PDK lag né certifica l'attuale predictor 2026/27.

## Stato dell'archiviazione prospettica

Ispezione read-only degli `archive_manifest.json` sotto `data/`: **5** archivi legacy GW1; **1** riporta `pre_lock_eligible=true` (`20261018T124836Z_e475d5d9`, schema archivio v1, `verified_fresh`), gli altri quattro sono `incomplete_evidence`. Il bundle eligible legacy ha forecast, lineups, coach e snapshot mercato/fixture/injury, ma non il contratto versionato corrente con `player_forecast_snapshot`, `runtime_feature_snapshot` e shadow snapshot. Non è pertanto equivalente al nuovo archivio di replay completo. Non ho trovato file `post_match_*.parquet` sotto `data/` (**0** al momento del controllo).

Il run GW3 usato nel report di audit precedente è non certificato: ID Dunkest mancanti, righe runtime ambigue e `archive_manifest.json` assente. Nessuno dei due fatti può essere riparato retroattivamente. La raccolta prospettica non è sufficiente a valutare i lag live finché un run naturale non supera il reviewer corrente e i relativi outcome ufficiali sono riconciliati.

## Esperimento minimo raccomandato

Non eseguibile in questa fase perché comporta training, escluso dal mandato. È la singola ablation da eseguire quando autorizzata:

| Braccio | Schema |
|---|---|
| Baseline | Trainer e schema live corrente; tutte le feature esistenti. |
| Variante unica | Stesso trainer, target, righe e feature, ma rimuovere solo `lag1_pdk`–`lag5_pdk` e `pdk_trend_3v10`; ogni altra feature e logica invariata. |

Protocollo: fold espandenti per date in development 2022/23–2024/25, stessa copertura per i due bracci, preprocessing/imputazione e selezione di pesi esclusivamente nel training/validation interno di ciascun fold. Riportare n e numero di date, MAE/RMSE/bias, bande di PDK previsto, PDK effettivo ≥25/≥30 come diagnosi, history count e coorte di cambiamento squadra/minuti quando le definizioni sono disponibili ex ante. Bootstrap appaiato per data su differenze di errore. Non ottimizzare soglie o pesi sul 2025/26 già esaminato; conservarlo al più come audit descrittivo. Per una decisione di produzione finale mantenere un holdout prospettico 2026/27 separato, con bundle e outcome verificati.

Se il blocco PDK viene rimosso senza peggiorare metriche e code, si potrà semplificare il modello; se migliora in modo stabile il baseline live, i lag sono utili come famiglia. Questo esperimento non stabilirà il contributo di ciascun lag individuale: per quello servirebbe una seconda fase di ablation, che aumenterebbe il numero di confronti e il rischio di selezione casuale.

## Criteri per adottare una variante

- stesso identico insieme di player-game e label ufficiali nei due bracci, senza chiavi duplicate o righe selezionate in base al risultato;
- feature calcolate solo da partite con data precedente e, dove disponibile, acquisizione precedente al cutoff; distinguere PDK official e proxy e riportarne la copertura;
- confronto nested temporale: nessun preprocessing, modello, peso o selezione feature addestrato sul fold test;
- metriche MAE/RMSE/bias complessive e per fasce **definite dal PDK previsto**; gruppi actual ≥25/≥30 solo diagnostici;
- differenze paired con intervalli bootstrap per data, stabilità fold-by-fold, numerosità e copertura;
- risultato di sviluppo non basta a promuovere: tenere un holdout prospettico indipendente non usato per selezionare la variante;
- nessun risultato è eleggibile finché il bundle pre-lock non passa il reviewer corrente, i riferimenti giocatore/partita sono univoci e l'outcome Dunkest ufficiale è riconciliato senza modificare il forecast.

## Risultati dimostrati, ipotesi e non verificabile

- **Dimostrato nei report salvati:** il blocco da 26 feature aggiunte (PDK, minuti, stats e conteggi) migliora pooled MAE/RMSE contro l'adapter 24 nei fold 2022/23–2024/25; i singoli lag PDK non sono isolati. L'arricchimento è già nel predictor live.
- **Ipotesi da testare:** togliere il trend ridondante o il blocco dei sei lag PDK può mantenere o migliorare il predictor live da 68 candidate columns; i lag possono risultare più utili in coorti con forma/ruolo in evoluzione.
- **Non valutabile ora:** confronto quantitativo attuale baseline live vs un'unica variante sullo stesso OOS; valore individuale di lag 1–5; disponibilità storica effettiva al cutoff di ogni label PDK lag; beneficio prospettico dei lag sulle rose.

## Stato e comandi eseguiti

La working tree era già modificata; non sono stati toccati file preesistenti. L'unico nuovo file è questo report. Comandi/letture in questa fase: `git status --short`, `rg -n` sui lag/report, `cat`/`sed` dei report, dei builder e dei test, e piccoli script read-only con `./.venv/bin/python` per differenza liste JSON delle feature e conteggio/sintesi di `archive_manifest.json` e `post_match_*.parquet`. Nessun test è stato eseguito: non è cambiato codice. Non sono state avviate suite, training, scraping o forecast. Nessun commit o push.
