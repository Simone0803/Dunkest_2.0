# HGB minuti — recency weighting walk-forward V1

Generato UTC: 2026-10-24T08:21:10.747826+00:00

## Ipotesi e protocollo

Intervento unico preregistrato: pesare il training HGB per recenza con emivita fissa di due anni (`2 ** (-age_years / 2)`). Non si aggiungono feature e non si cambiano estimator, imputazione o schema. I fold 2022/23–2024/25 misurano robustezza storica; il 2025/26 è il test finale minuti separato e non seleziona l'intervento. In ogni fold il training termina prima della prima data di test; le mediane e gli encoder sono rifittati sul solo training.

## Dati e copertura

Dataset base: 112,178 righe; dopo link target verificato e date valide: 112,165. Righe senza label escluse: 13. Righe finali hanno ID Dunkest, `nba_GAME_ID` e `nba_PLAYER_ID` univoci. 2018/19 e 2019/20 sono esclusi perché le etichette ufficiali Dunkest non sono valide; dati 2020/21–2025/26 sono presenti. Il 2025/26 usa il crosswalk ufficiale locale univoco (`gameValidForDunkest=True`, `matched_name_date_opponent`).

## Risultati appaiati

Cohort comune: 76,094 player-game, 4,136 partite. Delta pooled recency − HGB iniziale: MAE +0.0075, RMSE +0.0092, bias +0.0168 minuti. IC 95% bootstrap appaiato per partita: `{"bias": [0.012930182624188522, 0.020651006823637616], "mae": [0.003998522484684908, 0.011053469049670838], "rmse": [0.005380194430765517, 0.013208925596915442]}`. Valore negativo di MAE/RMSE favorisce recency; bias è differenza tra i bias dei modelli.

### Per fold

| fold | n | games | initial_MAE | recency_MAE | delta_MAE | initial_RMSE | recency_RMSE | delta_RMSE | initial_bias | recency_bias | CI95_delta_MAE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022-23 | 19165 | 1042 | 5.0915 | 5.0867 | -0.0048 | 6.6028 | 6.6084 | 0.0056 | 0.3038 | 0.3377 | [-0.011441639927598123, 0.0017285605944685068] |
| 2023-24 | 18927 | 1013 | 5.0087 | 5.0375 | 0.0288 | 6.4208 | 6.4448 | 0.0240 | 0.4004 | 0.4503 | [0.021846853414268265, 0.03551370935215483] |
| 2024-25 | 19590 | 1038 | 4.8522 | 4.8500 | -0.0022 | 6.3295 | 6.3290 | -0.0005 | 0.1633 | 0.1339 | [-0.009528332827767971, 0.004829834067856236] |
| 2025-26 | 18412 | 1043 | 4.8062 | 4.8150 | 0.0089 | 6.2631 | 6.2711 | 0.0080 | 0.2491 | 0.2633 | [0.0021816307289511004, 0.015324083393414574] |

### Baseline prev5 sul sottoinsieme comune con storico disponibile

| Coorte (campione condiviso) | N | Partite | MAE | RMSE | Bias |
|---|---:|---:|---:|---:|---:|
| Tutti i fold: prev5 | 75848 | 4136 | 5.0947 | 6.7280 | 0.0467 |
| Tutti i fold: HGB iniziale | 75848 | 4136 | 4.9313 | 6.3955 | 0.2786 |
| Tutti i fold: HGB recency | 75848 | 4136 | 4.9389 | 6.4047 | 0.2959 |
| 2025/26: prev5 | 18348 | 1043 | 4.9935 | 6.5595 | 0.0947 |
| 2025/26: HGB iniziale | 18348 | 1043 | 4.7948 | 6.2465 | 0.2571 |
| 2025/26: HGB recency | 18348 | 1043 | 4.8037 | 6.2546 | 0.2711 |

IC 95% bootstrap appaiato per partita delle differenze HGB − prev5: pooled HGB iniziale `{"bias": [0.2073516226433205, 0.2564967737471622], "mae": [-0.18244237224717266, -0.14495958997607286], "rmse": [-0.35605317674273435, -0.30963842246220746]}`; pooled HGB recency `{"bias": [0.22484808208118018, 0.2747369178190228], "mae": [-0.17380278646412695, -0.13679426457142355], "rmse": [-0.3448757324179196, -0.29948873999069553]}`; test finale 2025/26 HGB iniziale `{"bias": [0.11484433758179644, 0.20796061514010392], "mae": [-0.23244035283610864, -0.1655574402676066], "rmse": [-0.36030544934864195, -0.2682796359218361]}`; HGB recency `{"bias": [0.12643091721061697, 0.22657340350314364], "mae": [-0.22276723959428943, -0.15707240784394041], "rmse": [-0.34968150236217205, -0.26165115141239564]}.

### Sottogruppi

| fold_id | fold | cohort | model | n_games | n | mae | rmse | bias_pred_minus_actual |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 | 2022-23 | zero_minutes_verified_label | hgb_initial | 42 | 48 | 11.7270 | 13.0740 | 11.7270 |
| 9 | 2022-23 | zero_minutes_verified_label | hgb_recency | 42 | 48 | 11.7058 | 13.1514 | 11.7058 |
| 9 | 2022-23 | positive_minutes | hgb_initial | 1042 | 19117 | 5.0748 | 6.5785 | 0.2751 |
| 9 | 2022-23 | positive_minutes | hgb_recency | 1042 | 19117 | 5.0700 | 6.5838 | 0.3091 |
| 9 | 2022-23 | low_history_lt5_proxy_not_rookie_label | hgb_initial | 242 | 384 | 5.9370 | 7.5744 | 0.1207 |
| 9 | 2022-23 | low_history_lt5_proxy_not_rookie_label | hgb_recency | 242 | 384 | 5.9045 | 7.5702 | 0.0430 |
| 9 | 2022-23 | history_ge5 | hgb_initial | 1042 | 18781 | 5.0742 | 6.5814 | 0.3076 |
| 9 | 2022-23 | history_ge5 | hgb_recency | 1042 | 18781 | 5.0699 | 6.5872 | 0.3437 |
| 9 | 2022-23 | actual_minutes_ge25 | hgb_initial | 1042 | 9470 | 4.6213 | 6.1636 | -3.1512 |
| 9 | 2022-23 | actual_minutes_ge25 | hgb_recency | 1042 | 9470 | 4.6001 | 6.1494 | -3.0922 |
| 13 | 2023-24 | zero_minutes_verified_label | hgb_initial | 48 | 71 | 9.9242 | 10.4187 | 9.9242 |
| 13 | 2023-24 | zero_minutes_verified_label | hgb_recency | 48 | 71 | 10.0360 | 10.5349 | 10.0360 |
| 13 | 2023-24 | positive_minutes | hgb_initial | 1013 | 18856 | 4.9902 | 6.4010 | 0.3646 |
| 13 | 2023-24 | positive_minutes | hgb_recency | 1013 | 18856 | 5.0187 | 6.4245 | 0.4143 |
| 13 | 2023-24 | low_history_lt5_proxy_not_rookie_label | hgb_initial | 287 | 434 | 5.9395 | 7.4334 | 0.2179 |
| 13 | 2023-24 | low_history_lt5_proxy_not_rookie_label | hgb_recency | 287 | 434 | 5.9666 | 7.4650 | 0.3655 |
| 13 | 2023-24 | history_ge5 | hgb_initial | 1013 | 18493 | 4.9868 | 6.3951 | 0.4047 |
| 13 | 2023-24 | history_ge5 | hgb_recency | 1013 | 18493 | 5.0157 | 6.4189 | 0.4523 |
| 13 | 2023-24 | actual_minutes_ge25 | hgb_initial | 1013 | 9168 | 4.5757 | 6.0234 | -2.9580 |
| 13 | 2023-24 | actual_minutes_ge25 | hgb_recency | 1013 | 9168 | 4.5719 | 6.0068 | -2.9673 |
| 19 | 2024-25 | zero_minutes_verified_label | hgb_initial | 44 | 59 | 10.6337 | 11.7958 | 10.6337 |
| 19 | 2024-25 | zero_minutes_verified_label | hgb_recency | 44 | 59 | 10.7074 | 11.8654 | 10.7074 |
| 19 | 2024-25 | positive_minutes | hgb_initial | 1038 | 19531 | 4.8348 | 6.3058 | 0.1317 |
| 19 | 2024-25 | positive_minutes | hgb_recency | 1038 | 19531 | 4.8323 | 6.3049 | 0.1019 |
| 19 | 2024-25 | low_history_lt5_proxy_not_rookie_label | hgb_initial | 240 | 404 | 5.1539 | 6.4948 | 0.3426 |
| 19 | 2024-25 | low_history_lt5_proxy_not_rookie_label | hgb_recency | 240 | 404 | 5.0613 | 6.4496 | 0.2069 |
| 19 | 2024-25 | history_ge5 | hgb_initial | 1038 | 19186 | 4.8459 | 6.3259 | 0.1595 |
| 19 | 2024-25 | history_ge5 | hgb_recency | 1038 | 19186 | 4.8455 | 6.3264 | 0.1323 |
| 19 | 2024-25 | actual_minutes_ge25 | hgb_initial | 1038 | 9475 | 4.5195 | 6.0628 | -2.9072 |
| 19 | 2024-25 | actual_minutes_ge25 | hgb_recency | 1038 | 9475 | 4.5331 | 6.0787 | -2.9266 |
| 25 | 2025-26 | positive_minutes | hgb_initial | 1043 | 18412 | 4.8062 | 6.2631 | 0.2491 |
| 25 | 2025-26 | positive_minutes | hgb_recency | 1043 | 18412 | 4.8150 | 6.2711 | 0.2633 |
| 25 | 2025-26 | low_history_lt5_proxy_not_rookie_label | hgb_initial | 275 | 440 | 5.5007 | 7.1309 | -0.1598 |
| 25 | 2025-26 | low_history_lt5_proxy_not_rookie_label | hgb_recency | 275 | 440 | 5.5156 | 7.1550 | -0.0742 |
| 25 | 2025-26 | history_ge5 | hgb_initial | 1043 | 17972 | 4.7892 | 6.2403 | 0.2592 |
| 25 | 2025-26 | history_ge5 | hgb_recency | 1043 | 17972 | 4.7979 | 6.2478 | 0.2715 |
| 25 | 2025-26 | actual_minutes_ge25 | hgb_initial | 1041 | 8587 | 4.4116 | 5.9095 | -2.8503 |
| 25 | 2025-26 | actual_minutes_ge25 | hgb_recency | 1041 | 8587 | 4.4090 | 5.9044 | -2.8650 |

## Baseline, PDK e limiti

La media degli ultimi cinque minuti è riportata solo sul suo sottoinsieme con valore disponibile; non viene chiamata modello ibrido. La formula ibrida di produzione non è ricostruibile fedelmente per queste partite: mancano snapshot storici as-of di ruolo Dunkest, gruppo lineup, crediti, disponibilità, concorrenza e allocazione per posizione. Per lo stesso motivo non si stima l'impatto PDK con una moltiplicazione minuti × rate. Rookie reali, cambi di squadra as-of, ruolo e disponibilità non sono etichette affidabili in questi record; sono marcati non valutabili. Il modello storico usa lo stesso estimatore HGB e parametri del componente shadow, ma non replica esattamente lo schema/preprocessing live: l’archivio storico usa lag estesi, imputazione con indicatori e one-hot; il predictor corrente usa `FEATURE_COLS` selezionate e `_fit_matrix`. La stima misura quindi una variante storica comparabile, non un replay esatto del modello operativo. I casi a zero sono solo target zero esplicitamente presenti nel log collegato.

## Decisione

**Scartare la modifica recency.** Nel test finale 2025/26 peggiora MAE di +0.0089 minuti (IC95% appaiato per partita `[0.0021816307289511004, 0.015324083393414574]`) e RMSE di +0.0080. La MAE migliora marginalmente in 2022/23 e 2024/25, ma peggiora in 2023/24 e 2025/26. HGB resta in shadow. Sul test 2025/26 l'HGB iniziale batte la baseline prev5 sul sottoinsieme comune, ma ciò non dimostra superiorità sull'ibrido di produzione. Nessuna promozione o modifica PDK è giustificata.

## Riproduzione

```bash
PYTHONPATH=src .venv/bin/python scripts/experiment_dunkest_minutes_hgb_recency_v1.py
```

Metriche: `reports/audit/dunkest_minutes_hgb_recency_walk_forward_20261024_v1_metrics.csv`; predizioni appaiate: `reports/audit/dunkest_minutes_hgb_recency_walk_forward_20261024_v1_predictions.csv`; audit macchina: `reports/audit/dunkest_minutes_hgb_recency_walk_forward_20261024_v1.json`.

No production model/config/optimizer changes; no commit or push.

