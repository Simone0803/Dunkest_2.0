# Dunkest 2.0 — esito della richiesta di ablation dei lag PDK

**Data:** 2026-10-26
**Esito operativo:** esperimento fermato prima di qualsiasi fit. Il training era autorizzato, ma le verifiche preliminari non consentono di riprodurre una baseline live completa e garantire la disponibilità temporale *as-of* per le osservazioni storiche. Non sono stati prodotti risultati nuovi.

## Perché l’esperimento è stato fermato

La specifica richiede insieme: predictor live, identico campione/fold/preprocessing, sola esclusione dei sei lag e nessuna informazione futura rispetto al cutoff. La verifica del codice conferma che il predictor operativo usa la stessa funzione `train_models` anche dal percorso multistagione, ma il dataset storico entra tramite un adapter e non contiene la provenienza temporale necessaria. Eseguire un confronto ora darebbe numeri su input ricostruiti per data, non una prova che quei PDK fossero disponibili al cutoff.

Inoltre il predictor operativo finale include passaggi successivi al fit (proiezione/blend OOF, calibrazione residua e correzione DvP); gli archivi storici non conservano gli input timestampati necessari per riprodurre questi passaggi completi sugli stessi incontri. Un fit sui dati adattati avrebbe quindi un nome simile al predictor live, ma non costituirebbe il confronto richiesto del forecast live completo.

## Verifiche riproducibili

- Stato Git esaminato prima di agire: working tree già modificata, con modifiche a pipeline/predictor/test e report/configurazioni locali non tracciati. Nessun file preesistente è stato ripristinato o sovrascritto.
- Specifica letta: `reports/audit/dunkest_pdk_lag_provenance_ablation_spec_20261026.md`.
- Percorso effettivo: `src/dunkest/pipeline/train.py` chiama `train_multiseason_models`; `src/dunkest/models/multiseason_training.py::train_multiseason_models` adatta il dataset storico con `adapt_certified_training_rows` e chiama `src/dunkest/models/predictor.py::train_models` sul target `target_pdk_official`.
- In quel percorso, stagioni supervised dichiarate: 2020/21–2024/25. Il 2025/26 è escluso dal default; gli outcome di quella stagione sono già stati consultati in analisi precedenti e non sono stati caricati né usati.
- Il trainer live seleziona colonne candidate di `FEATURE_COLS` in base alla disponibilità nel fold, esegue imputazione fold-local e apprende l’ensemble/calibrazione tramite OOF. L’adapter assegna `NaN` a feature storiche non supportate e `expected_pdk_minutes_model=0`; perciò non garantisce la stessa matrice informativa del run operativo corrente.
- `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet` non contiene colonne `observed/acquired/timestamp/captured/fetch/retriev/publish`; lo stesso vale per le tabelle storiche ufficiali e per l’overlay bulk verificati nella preparazione precedente. Il metadata bulk dell’API non dà l’acquisizione per singolo game/label.
- Il feature builder (`src/dunkest/features/builder.py`) ordina le partite e costruisce i lag solo da righe precedenti per data; preferisce PDK ufficiale e ripiega sul proxy. Questo evita l’inclusione della partita target in base alla data, ma non prova che il valore precedente fosse stato acquisito prima del cutoff storico. Neppure l’origine ufficiale/proxy è tracciata per ogni singolo valore lag nel dataset usato.
- I timestamp round-level 2026/27 disponibili coprono solo snapshot correnti di GW1/GW2. Non attestano retroattivamente la disponibilità delle label nei fold 2022/23–2024/25 e non forniscono gli input completi delle previsioni live storiche.
- L’archivio GW1 legacy non contiene outcome ufficiali riconciliati secondo il contratto corrente; il run GW3 `20261025T101251Z_6d20853d` è diagnostico/non eleggibile. Non sono utilizzabili per il confronto richiesto.

## Confronto non eseguito

| Braccio previsto | Definizione | Esito |
|---|---|---|
| A — baseline | Predictor live attuale, con tutte le feature live | Non riproducibile sui fold storici con la matrice/runtime/DvP e provenienza pre-cutoff equivalenti. |
| B — ablation | Stesso predictor, eliminando esclusivamente `lag1_pdk`–`lag5_pdk` e `pdk_trend_3v10` | Non eseguito: senza un braccio A valido e senza cutoff storico verificabile, il confronto appaiato sarebbe fuorviante. |

Non sono state calcolate MAE, RMSE, bias, metriche per bande, differenze B−A o intervalli di confidenza. Non sono state riutilizzate le metriche dell’ablation del 14 ottobre come se fossero questo esperimento: quella confrontava 24 feature adapter con 50 feature arricchite, includendo altre 20 feature oltre ai sei lag PDK.

## Dati necessari per riprendere

1. Snapshot prospettici versionati, creati prima del cutoff, con feature effettivamente viste dal predictor, ID stabili player-game, PDK ufficiali dei lag e timestamp di acquisizione/provenienza per ciascuna riga. Il bundle deve superare il reviewer corrente.
2. Outcome Dunkest ufficiali acquisiti dopo le partite e riconciliati separatamente sugli stessi ID.
3. Un holdout prospettico sufficiente con più giornate. Il 2025/26 consultato e i fold storici senza timestamp non possono fungere da holdout certificato.
4. Per un eventuale esperimento storico secondario, dichiarare prima che misura solo l’ablation del trainer adattato *event-time*, non la disponibilità reale al cutoff e non il forecast operativo completo. In quel protocollo si devono congelare codice/configurazione, target e campione, applicare gli stessi fold e trasformatori, usare la stessa procedura OOF in entrambi i bracci e rimuovere esclusivamente i sei campi. Tale risultato non deve essere promosso come validazione live.

## Raccomandazione

**1. Mantenere i lag invariati in produzione**, in attesa di una prova prospettica valida. È una decisione prudenziale dovuta all’assenza del confronto richiesto, non una conclusione che i lag migliorino o peggiorino il predictor. Quando esisteranno snapshot pre-lock e outcome riconciliati, eseguire i due bracci appaiati; accettare un contributo solo se MAE/RMSE e bias sono robusti tra fold/giornate, gli intervalli appaiati supportano un beneficio pratico e le fasce di PDK previsto/coorti prioritarie non mostrano regressioni.

## Comandi ed effetti di questa operazione

Eseguiti: `git status --short`; lettura della specifica e dei percorsi `train.py`, `multiseason_training.py`, `predictor.py`; `rg` mirato alle colonne/target/lag. Non eseguiti: training, scraping, forecast, tuning e test del modello. Nessun codice, modello, configurazione, feature, archivio o report storico è stato modificato. È stato creato solo questo report. `git diff --check` e controllo whitespace del nuovo file sono stati eseguiti; nessun commit o push.
