# Implementazione dei tre workstream Dunkest — 2026-10-14

## 1. Trainer multi-stagione principale

- Integrato `train_multiseason_models` nel percorso della Giornata 1 sia in `pipeline/season_opener.py` sia in `pipeline/train.py`.
- Fonte target: `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet`; solo target ufficiali certificati `gameValidForDunkest=True` delle stagioni 2020/21–2024/25.
- Righe effettive del trainer: 93.766, dal 2020-12-22 al 2025-04-11. La 2025/26 resta la sorgente delle feature di inferenza per la G1, non è target di training.
- Le stagioni 2018/19 e 2019/20 non vengono usate come target Dunkest: il flag ufficiale di validità è falso. La loro storia NBA può essere usata nei lag storici del dataset, senza trasformare i punteggi non validi in etichette.
- Pesi limitati per poca storia: 1,25 per `history_games_before_target <= 5`, 1,10 fino a 10, 1,00 altrimenti. Il manifest della run registra `sample_weighted_training=true`, media pesi 1,0176 e la policy applicata.
- Il trainer fallisce in modo esplicito se manca il dataset certificato, se le chiavi stagione/giocatore/partita sono duplicate o se il cutoff supera il 2024/25. Le configurazioni versionate forzano `training_target: target_pdk_official`.
- Il modello multi-stagione produce predizioni PDK assolute; la pipeline non aggiunge una seconda volta il baseline dei minuti.

### Validazione walk-forward del training window

Esperimento Ridge a parità di adapter/feature, con tuning solo sui fold temporali del training. Il bootstrap appaiato è raggruppato per data.

| Test season | MAE solo stagione precedente | MAE multi-stagione | Δ MAE multi − singola | IC 95% bootstrap |
|---|---:|---:|---:|---|
| 2022/23 | 7,585 | 7,575 | −0,0091 | [−0,0139; −0,0047] |
| 2023/24 | 7,595 | 7,576 | −0,0189 | [−0,0256; −0,0111] |
| 2024/25 | 7,651 | 7,633 | −0,0181 | [−0,0250; −0,0105] |
| 2025/26 | 7,633 | 7,605 | −0,0282 | [−0,0331; −0,0228] |

I pesi per poca storia migliorano ulteriormente il MAE di 0,0010–0,0018 nei fold, con intervalli bootstrap che non includono zero. Il bias diventa però più negativo con la finestra multi-stagione (nel fold 2025/26: −0,279 contro −0,017), quindi il solo MAE non è sufficiente per dichiarare conclusa la calibrazione. La coorte `history_games_before_target <= 5` è un proxy di poca storia, non un'etichetta certificata di rookie NBA. La 2025/26 è già stata esaminata in esperimenti precedenti e non è un holdout globale intatto.

Script: `scripts/validate_dunkest_multiseason_production_adapter_v3.py`. Report completo: `reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v3.md`.

## 2. Leakage temporale e calibrazione

- Le feature di training dell'adapter sono costruite da colonne laggate/storiche; il target ufficiale e le statistiche della partita corrente non sono feature.
- Le date dei fold sono ordinate cronologicamente e il validatore interrompe l'esperimento se training e test si sovrappongono temporalmente.
- L'imputazione viene stimata dentro ogni fold; il tuning Ridge usa il primo fold, escluso dalla calibrazione OOF.
- Corretto un bug nella calibrazione: le righe senza previsioni OOF valide potevano entrare nei residui e nel fallback della proiezione. Ora si usano solo predizioni OOF valide; il fold senza un precedente slate OOF usa una proiezione predefinita ensemble-only. Le diagnostiche sono calcolate sulle stesse previsioni proiettate usate per ottenere i residui.
- I quantili empirici OOF non vengono riscalati una seconda volta dalla deviazione standard storica del singolo giocatore; il riscalamento resta disponibile soltanto per il fallback gaussiano quando mancano quantili empirici.

Manifest della run finale `data/predictions/20261014T104418Z_49f79e8c/manifest.json`:

- Residui OOF: 38.517 osservazioni; quantili P10/P50/P90 = −10,642 / −1,008 / +13,621 PDK.
- Copertura nella stessa calibrazione cross-fitted: P10 = 90,00%, P90 = 90,00%, ampiezza media = 24,26 PDK.
- Le coorti con poca storia mostrano copertura superiore al 94%, quindi gli intervalli sono ancora conservativi per tali gruppi. Queste sono diagnostiche OOF di training, non misure su un test indipendente.
- Il join overlay ufficiale della feature season 2025/26 ha associato 24.052/24.100 righe NBA; le 48 non abbinate restano senza target ufficiale e non vengono riempite con proxy.

Test aggiunto per impedire la regressione della calibrazione: `test_cross_fitted_calibration_uses_only_valid_oof_residuals`.

## 3. Punteggio reale della rosa e backtest

- Aggiunto `src/dunkest/backtest/realized_scoring.py`: richiede esattamente 10 giocatori, tutti i punteggi effettivi, punteggio coach verificato sul fixture, conteggio trasferimenti noto e malus non negativo. Applica gli slot Dunkest (titolari, capitano, sesto uomo, panchina) e sottrae il malus trasferimenti. Dati mancanti o link coach non verificato restituiscono una valutazione incompleta, mai un totale parziale.
- Integrato il calcolo nel walk-forward backtest. Test dedicati coprono capitano/sesto uomo/panchina, coach, malus, assenza di risultati e conteggio trasferimenti sconosciuto.
- Eseguito `run-backtest.sh --config config/backtest.example.yaml --from-gw 1 --to-gw 10`. Il backtest si è fermato correttamente con `Backtest non pronto — nessuna metrica lineup prodotta`: mancano mapping fixture provati, snapshot prepartita di roster/CR/infortuni/coach e risultati player/coach collegati alle fixture. L'inventario storico conferma che tali snapshot non sono disponibili per le stagioni archiviate esaminate.
- Di conseguenza, il **motore di scoring completo è implementato**, ma non è possibile certificare una metrica storica di squadra completa finché non esistono snapshot prepartita autentici e risultati fixture-linked. I backtest proxy già presenti non sono promossi a prova di accuratezza reale.

## Verifica della run di produzione

Run: `data/predictions/20261014T104418Z_49f79e8c/`.

| Rosa | PDK previsti | CR giocatori | CR coach | CR totale | Capitano | Solver |
|---|---:|---:|---:|---:|---|---|
| 1 | 230,09 | 87,5 | 7,5 | 95,0 | Jayson Tatum | Optimal |
| 2 | 220,80 | 87,5 | 7,5 | 95,0 | Evan Mobley | Optimal |
| 3 | 217,97 | 89,0 | 6,0 | 95,0 | Walker Kessler | Optimal |

Controlli su tutte e tre: 10 giocatori, budget totale rispettato, nessun giocatore mancante dal mercato, nessun indisponibile duro tra gli selezionati, tre capitani distinti. Le rose non sono indipendenti tra loro e le proiezioni non sono risultati realizzati.

## Test e stato Git

- `PYTHONPATH="$PWD/src" .venv/bin/python -m pytest -q`: **312 passed**, 6.800 warning (principalmente deprecazioni PuLP/CBC e un warning di test sui metadata freshness).
- `git diff --check`: nessun errore.
- Nessun commit o push effettuato.

## 4. Confronto esteso dei modelli (14 ottobre 2026)

Report riproducibile: `reports/audit/dunkest_model_comparison_20261014_v2.md`; script: `scripts/compare_dunkest_models_by_season_cohort_v1.py`.

- Confronto su 76.094 righe di test complessive nelle stagioni 2022/23–2025/26: multi-season MAE 7,598 e RMSE 9,900; single-season MAE 7,616 e RMSE 9,895; baseline media ultimi 10 punteggi MAE 7,779 e RMSE 10,137. Il multi-season riduce il MAE rispetto a single-season in tutti i quattro fold, ma non migliora l'RMSE aggregato e ha bias medio più negativo (−0,398 contro −0,119 PDK).
- L'intervallo bootstrap appaiato per cluster di data supporta il miglioramento MAE multi-season in ogni fold: differenze multi meno single da −0,009 a −0,028 PDK; tutti gli intervalli al 95% sono sotto zero.
- Il peso per poca storia migliora il MAE di appena 0,001–0,002 PDK in media, ma rende il bias più negativo. Non c'è evidenza sufficiente per aumentare ulteriormente tali pesi.
- Per i rookie identificati tramite draft year, i miglioramenti multi-season rispetto a single-season non sono statisticamente chiari in due fold su quattro; il vantaggio rispetto alla baseline prev10 non è chiaro in due fold su quattro. Le coorti hanno circa 1.200–1.700 righe di gioco per fold e includono intervalli bootstrap per data, ma la corrispondenza nome/draft year non equivale a una certificazione della stagione di debutto NBA.
- Le categorie di ruolo/posizione non sono state confrontate perché il dataset ufficiale certificato non contiene una posizione storica affidabile. Sono invece riportate coorti per storia Dunkest (0, 1–5, 6–10, oltre 10 partite).
- Il confronto è diagnostico del training window con Ridge e adapter di produzione, non una validazione indipendente dell'intero ensemble. La stagione 2025/26 è già stata esaminata in esperimenti precedenti e non è un holdout globale intatto. Nessun parametro o artefatto di produzione è stato modificato.
- Test dopo l'aggiunta del confronto: **312 passed**, 6.800 warning; `git diff --check` e compilazione dello script superati.

## 5. Ensemble, calibration, matchup and optimizer audit (14 October 2026)

Consolidated report: `reports/audit/dunkest_optimizer_ensemble_calibration_matchup_20261014_v1.md`.

- Existing OOS ensemble-weight search selected RF 0.60 / Ridge 0.35 / previous-10 PDK mean 0.05 on 2022/23–2024/25 only. Validation MAE was 7.5658. The 2025/26 result is historical evidence, not a globally untouched holdout; production weights remain unchanged.
- Existing train-only hyperparameter search selected Extra Trees deep with validation MAE 7.5635 versus RF 7.5880, a small improvement. The candidate is not integrated because its feature schema is not wired to production inference.
- New expanding-origin uncertainty audit uses only previous-season residuals to calibrate each test fold. Pooled interval lower/upper marginal coverage was about 89.5–90.5%, with central 80% coverage 79.8–80.4%. Cohort quantiles narrow low-history intervals (2025/26 width 15.62 vs 24.20 PDK pooled) with 79.77% central coverage, but remain an RF proxy; no production calibration changed. First audit version had an interval sign inversion and is explicitly superseded by `_v2`.
- Coach Platt calibration worsened validation Brier and log loss; do not deploy. NBA appearance-continuity proxy has a 99.64–99.79% positive rate among observed rows and cannot validate Dunkest availability probability.
- Player role-conditioned matchup interactions showed effectively zero game-level gain (paired MAE delta −0.000055; 95% CI [−0.004265, +0.004187]). H2H lineup variant was worse by 5.66 proxy team points/round (95% CI [−9.49, −1.77]); neither is promoted.
- Rest/schedule lineup challenger gain was +1.56 proxy points/round with 95% CI [−1.95, +5.08]. Transfer optimizer coefficient 2.5 vs 5.0 was inconclusive (+0.32, CI [−2.42, +3.01]). Frozen GW1 strategy snapshots were 149–151 hours old, above the 36-hour limit; not decisive.
- No production weights, risk lambda, scoring coefficients, probability calibrator, or matchup feature changed. The follow-up OOS audit and final verification are recorded in section 6 below.


## 6. Production ensemble OOS validation and lineup-data readiness (14 October 2026)

New detailed report: `reports/audit/dunkest_production_ensemble_and_lineup_validation_20261014_v1.md`.

### Core production ensemble

- New script: `scripts/audit_dunkest_production_ensemble_expanding_oos_v1.py`.
- Re-trained the exact production `train_models` model zoo independently for each test season, using only certified earlier seasons. Test folds cover 2021/22–2025/26; each training cutoff is strictly before the test season. Interval quantiles use only earlier seasons' OOS residuals.
- Core ensemble MAE / RMSE: 2021/22 7.880 / 10.198; 2022/23 7.563 / 9.873; 2023/24 7.557 / 9.840; 2024/25 7.607 / 9.920; 2025/26 7.587 / 9.874. The previous-10 baseline MAE is 8.094, 7.764, 7.755, 7.783 and 7.782 respectively. Model MAE is better in every fold; mean bias remains negative after 2021/22.
- Pooled prior-OOS residual intervals achieved central 80% coverage 82.30%, 81.15%, 80.72% and 80.70% for 2022/23–2025/26, with marginal tail coverage close to 90%.
- For players with 0–5 prior Dunkest rows, cohort-specific quantiles narrowed mean interval width to about 17.2–17.4 PDK from pooled widths of 24.6–25.5 PDK while central coverage stayed at 80.4–82.0%. This is a challenger only: the final inference layer adds market-specific minutes, a historical PDK blend, rookie priors and availability weighting, which cannot be reproduced over complete historical rounds without authentic pre-lock snapshots. Do not promote the cohort calibrator yet.
- The 6–10 history cohort is not stable enough for deployment; its 2025/26 cohort-specific central coverage was 77.52%. 2025/26 is not a globally untouched holdout.

### Full-lineup strategy comparison

- Snapshot inventory found 54 repeated saved copies of `player_credits_26_gw1.parquet`, `coach_market_26_gw1.parquet` and `injuries_26_gw1.parquet`, all for 2026/27 Gameweek 1. There are no matching historical pre-lock market/coach/injury snapshots in `data/processed` for archived seasons.
- Historical CR values in round-level player records are not certified as pre-lock prices. They are not substituted for authentic snapshots.
- Frozen GW1 strategy runs were 149–151 hours before earliest kickoff, failing the strict 36-hour freshness gate. The current optimizer objective and risk lambda therefore remain unchanged; proxy lineup comparisons are not treated as realized strategy evidence.
- Next valid comparison requires complete snapshots within 36 hours before lock, followed by verified player and coach actuals, fixture links and known transfer state; compare paired rounds with round-cluster bootstrap intervals.

### Verification and state

- `PYTHONPATH="$PWD/src" .venv/bin/python -m pytest -q`: **312 passed, 6,800 warnings**.
- `git diff --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m py_compile scripts/audit_dunkest_production_ensemble_expanding_oos_v1.py`: passed.
- No production model/configuration, uncertainty calibration, lineup objective, risk lambda or scoring rule was changed. No commit or push was performed.
