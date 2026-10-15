# Dati locali e backtest

La directory `data/` è esclusa dal controllo versione: può contenere grandi dataset e cache locali. I backtest storici devono usare dati reali archiviati, non log sintetici e non il listino corrente al posto di quello storico.

## Snapshot richiesti per ogni giornata

Per la stagione Dunkest `SID` e la giornata `GW`, il backtest verifica questi file sotto `data/processed/`:

- `dunkest_fixture_mapping_SID_*.parquet`: mapping NBA–Dunkest con provenienza, timestamp precedente alla partita, mapping verificato e identificativi NBA.
- `player_credits_SID_gwGW.parquet`: rosa, ruoli e CR archiviati prima della giornata.
- `injuries_SID_gwGW.parquet`: snapshot indisponibili con giocatore, squadra, stato e giornata.
- `coach_market_SID_gwGW.parquet`: coach, squadra, CR, avversario, data, NBA game ID e fonte del fixture.
- `dunkest_players_SID_gwGW.parquet`: risultati giocatore con `actual_pdk`, `gameweek_stats_available` e `nba_game_id`.
- `dunkest_coach_results_SID_gwGW.parquet`: risultati coach con `team`, `nba_game_id` e `actual_coach_pdk`.

Sono inoltre necessari log NBA reali per la stagione configurata, conservati o recuperabili tramite la NBA API. I file con nomi diversi non sono automaticamente equivalenti: non rinominare snapshot per far passare i controlli. La readiness del programma verifica colonne e collegamenti tra identità prima di calcolare metriche.

## Preparare ed eseguire

Dalla radice del repository:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
bash ./run-backtest.sh --config config/backtest.example.yaml --from-gw 1 --to-gw 10
```

La configurazione d'esempio usa Dunkest season ID `25` / NBA 2025-26. Usala solo se gli snapshot in `data/processed/` corrispondono a quella stagione. Per una stagione diversa, crea una copia della configurazione e aggiorna almeno `season`, `season_id` e le date NBA.

Se uno o più snapshot mancano, il comando elenca i controlli falliti e termina con codice d'errore, senza presentare metriche di rosa come risultati validi. Gli snapshot prepartita non possono essere ricostruiti fedelmente a posteriori dal listino odierno; raccoglili prima delle giornate future e conserva i risultati ufficiali a giornata conclusa.


## Archivio storico Dunkest e modello PDK sperimentale

La raccolta storica dei risultati ufficiali Dunkest e i relativi controlli sono documentati in [reports/audit/dunkest_historical_data_training_2018-25_v1.md](../reports/audit/dunkest_historical_data_training_2018-25_v1.md). Il dataset weekly-round copre le Regular Season 2020/21–2024/25; la cronologia per partita via API ufficiale include anche 2018/19 e 2019/20, ma il flag `gameValidForDunkest` è sempre `False` in quelle due annate e i relativi PDK non sono quindi usati come target nel training rigoroso.

I dataset e gli artefatti `dunkest_pdk_historical_random_forest_2020-25_v1/v2` sono esperimenti separati, non usati dalla pipeline di produzione. La V2 usa le statistiche NBA dell'ultima partita precedente alla data target, con controlli anti-leakage e walk-forward per stagione. Prima di integrare un modello, consultare il report, ripetere la validazione su dati prospettici e verificare il significato dei flag storici.


## Target PDK ufficiale nella pipeline

Durante il training, la pipeline cerca l'overlay locale versionato
processed/player_game_logs_<stagione>_official_pdk_overlay_v4.parquet (oppure il
nome legacy senza _v4). L'overlay viene associato ai log NBA tramite ID giocatore,
ID partita, data e squadra; il join è uno-a-uno e non modifica la colonna PDK
proxy già usata per le feature storiche. Le righe senza un target ufficiale restano
senza etichetta ufficiale.

Le configurazioni versionate `config/default.yaml` e `config/season_opener.yaml`
forzano `training_target: target_pdk_official`: se il target ufficiale manca o non
contiene etichette finite, il training si interrompe invece di ripiegare sul proxy.
La modalità `auto` resta disponibile per chiamate esplicite a `Settings` e sceglie
il target ufficiale solo con almeno 1.000 etichette finite.

Per la prima giornata, `opening_multiseason_training: true` attiva il trainer
multi-stagione principale. Usa le 93.766 righe ufficiali certificate del dataset V3
per le stagioni 2020/21–2024/25, con feature laggate e pesi moderati per i giocatori
con poca storia (1,25 fino a 5 partite storiche; 1,10 fino a 10; 1,00 altrimenti).
La stagione 2025/26 resta la fonte per costruire le feature di inferenza della G1,
ma non è un target del trainer. Le stagioni 2018/19 e 2019/20 non sono usate come
target Dunkest perché `gameValidForDunkest=False`; possono contribuire come storia
NBA verificata alla costruzione dei lag, non come etichette supervisionate.
L'adapter fallisce in modo esplicito se il dataset manca, contiene chiavi duplicate
o supera il cutoff 2024/25. Per disattivare questa modalità solo in modo intenzionale,
imposta `opening_multiseason_training: false` nella configurazione.

## Training storico PDK V3 (fino alla stagione 2025/26)

Dataset: `processed/dunkest_pdk_game_training_2020-26_v3.parquet` (112.178 righe etichettate). Il dataset aggiunge 18.412 target ufficiali 2025/26 con `gameValidForDunkest=True` e corrispondenza univoca al log NBA. Tutte le feature PDK/NBA delle righe storiche V2 sono rimaste identiche nella ricostruzione V3.

Modello storico separato: `processed/dunkest_pdk_historical_random_forest_2020-26_v3.joblib`. L'artefatto RF conserva la propria valutazione walk-forward e resta un componente separato dell'ensemble; il trainer principale della G1 ora usa invece l'adapter V3 con Ridge/RF/Gradient Boosting e feature compatibili con la pipeline di produzione.

Report dataset: `../reports/audit/dunkest_historical_data_training_2018-26_v2.md`. Con l'adapter di produzione, un confronto Ridge a finestra mobile (stesso learner, stesso adapter) ha ridotto il MAE multi-stagione rispetto alla sola stagione precedente in tutti i fold 2022/23–2025/26. Sul fold 2025/26 il MAE è 7,605 contro 7,633 (bootstrap per data 95% CI della differenza: [-0,0331, -0,0228]); il bias diventa però più negativo (-0,279 contro -0,017), mentre l'RMSE cambia poco. La stagione 2025/26 è già stata esaminata in esperimenti precedenti e non è un holdout globale intatto: i numeri sono evidenza di validazione storica, non una garanzia di accuratezza prospettica.


## Prior rookie su target ufficiale Dunkest

Il file locale `data/rookie_official_pdk.csv` contiene un'etichetta per giocatore e classe draft: PDK ufficiali aggregati divisi per minuti giocati nella prima stagione Dunkest verificata successiva al draft. Le etichette provengono da `processed/dunkest_pdk_game_training_2020-26_v3.parquet` e dai log ufficiali associati; il builder verifica la corrispondenza dei punteggi e richiede join univoci su ID giocatore/partita oppure nome normalizzato/partita.

Sono incluse solo le classi 2020–2025 perché il target ufficiale validato parte dalla stagione 2020/21. Per ogni giocatore viene scelta la prima stagione con una presenza Dunkest ufficiale dopo il draft, così un debutto NBA ritardato non viene erroneamente trattato come una stagione senza rendimento. I giocatori senza una presenza verificata restano senza etichetta: non vengono trasformati artificialmente in zeri.

Rigenerazione riproducibile dalla radice del repository:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_official_rookie_pdk_labels_v1.py --force
```

La pipeline del prior usa questo target solo quando ci sono almeno 40 etichette ufficiali su almeno quattro classi; altrimenti ricade sul target proxy NBA storico. Il target ufficiale e il proxy non vengono mescolati nella stessa regressione. La fonte selezionata è esposta nella colonna `college_target_source` delle previsioni.

## Validazione plusvalenza CR-adaptive

Il modello di conversione della variazione di CR è validato con origine temporale espandente, usando ogni quinta giornata osservata per confrontare regressione Ridge ed ExtraTrees senza allenare su giornate future. La policy corrente usa ExtraTrees per CR sotto 5, un blend 50/50 per CR da 5 incluso a 9 escluso e Ridge da 9 CR in su: il modello non lineare è più utile sui prezzi bassi, mentre extrapola peggio sui prezzi elevati.

Nell'audit walk-forward campionato su 7.436 righe, la MAE è scesa da 0,07172 CR con Ridge a 0,06984 CR con la policy adattiva; la calibrazione del bias per fascia di credito, stimata solo sui fold precedenti, porta la MAE a 0,06843 CR contro una baseline di circa 0,179 CR. I residui sono in unità CR e vengono aggiunti dopo la conversione score→ΔCR: non vengono più applicati al punteggio PDK, evitando un errore di unità che comprimeva gli intervalli e distorceva le probabilità. Le probabilità di guadagno restano in verifica: nel test conversion-only il Brier score è 0,0602, con una sovrastima media del guadagno di circa 3,3 punti percentuali. Queste sono metriche del forecast one-step della variazione CR, non una dimostrazione del miglioramento del punteggio finale delle rose: per quest'ultima servono backtest di roster con snapshot prepartita verificati.

## Ricostruzione dei punteggi storici per turno da log ufficiali

Per il backtest storico delle rose non si assume più che l'assenza di una riga nell'aggregato settimanale equivalga automaticamente a zero. La ricostruzione usa la data del turno accettata solo quando almeno il 75% dei collegamenti giocatore-data concorda e ci sono almeno 10 giocatori collegati; poi somma i PDK ufficiali delle partite Dunkest-valide in quella stagione/data. La verifica rigorosa V2 ha confrontato 93.734 righe giocatore-turno: 93.728 coincidono con l'aggregato storico entro 0,02 PDK (99,994%), MAE 0,00149 PDK. La versione che univa indiscriminatamente tutti gli ID partita per turno è stata marcata superseded per collisioni di box score tra date diverse.

Script del confronto rose con actuals ricostruiti e training strettamente pre-target: `scripts/backtest_dunkest_historical_lineups_gamelevel_actuals_v3.py`. Il risultato resta un proxy, non un backtest certificato dell'intera strategia: crediti/ruoli/team pre-lock sono lagged, l'universo storico non è completo, i coach usano CR neutro 10 e il malus trasferimenti è escluso.

## Archivio prospettico pre-lock

Dopo aver generato le previsioni, si può certificare e archiviare un run solo se gli snapshot mercato, infortuni, allenatori e disponibilità sono datati, le partite sono collegate e il run è entro 36 ore dal primo kickoff:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/archive_dunkest_pre_lock_run_v1.py --run-id <RUN_ID> --max-age-hours 36
```

Il comando non sovrascrive archivi esistenti, registra hash SHA-256 e fallisce chiuso se le evidenze sono incomplete o stale. Il run GW1 del 14/10/2026 è stato correttamente rifiutato perché acquisito circa 133 ore prima del primo kickoff.
