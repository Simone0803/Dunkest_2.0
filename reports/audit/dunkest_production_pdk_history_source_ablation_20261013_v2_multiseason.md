# Multi-season production PDK history-source ablation

Generated UTC: 2026-10-13T10:15:26.838766+00:00

## Protocol

- Seasons: 2021/22–2025/26. Each season is evaluated with its own expanding chronological OOF folds using the production feature builder and model trainer.
- Both arms use identical verified official PDK target labels.
- Proxy arm uses NBA-boxscore PDK for rolling features/baselines.
- Challenger uses official Dunkest PDK for rolling features wherever a verified match exists, with proxy fallback for unmatched NBA games.
- 2025/26 is descriptive only and excluded from the validation-season bootstrap.
- Production files/configuration and raw datasets were not modified.

## Metrics by season and feature source

 season                                 mode  n_official_labels  n_oof      mae      rmse  bias_pred_minus_actual  within_3_pdk_pct  within_5_pdk_pct                                                                         model_weights                                                                                projection_weights
2021-22                        proxy_history              18416   7448 7.957723 10.223502               -0.166257         25.026853         39.191729  {"gbr": 0.33250987862638987, "rf": 0.33472613429749676, "ridge": 0.3327639870761134}       {"ensemble": 0.7587603032320208, "minutes": 0.05105982286918921, "prior": 0.19017987389879}
2021-22 official_history_with_proxy_fallback              18416   7448 7.953436 10.218423               -0.206282         24.879162         39.151450   {"gbr": 0.33253405001931086, "rf": 0.3345636975580272, "ridge": 0.3329022524226619}   {"ensemble": 0.8427306200748249, "minutes": 0.008407347626638629, "prior": 0.14886203229853645}
2022-23                        proxy_history              19165   7427 7.628449  9.959719               -0.410847         26.457520         42.305103  {"gbr": 0.33375697397875165, "rf": 0.33314427536665586, "ridge": 0.3330987506545924} {"ensemble": 0.9216249327285327, "minutes": 4.6663308463447113e-17, "prior": 0.07837506727146726}
2022-23 official_history_with_proxy_fallback              19165   7427 7.628940  9.961220               -0.417590         26.430591         42.439747  {"gbr": 0.33407572053558793, "rf": 0.3328438607215715, "ridge": 0.33308041874284056} {"ensemble": 0.8969616189450308, "minutes": 1.6526931128131916e-16, "prior": 0.10303838105496907}
2023-24                        proxy_history              18927   8112 7.478637  9.766440                0.018099         26.565582         43.306213  {"gbr": 0.3329557732958954, "rf": 0.33300186748875604, "ridge": 0.33404235921534864}    {"ensemble": 0.8164267592328646, "minutes": 0.05003842409670096, "prior": 0.13353481667043457}
2023-24 official_history_with_proxy_fallback              18927   8112 7.474072  9.762627                0.015540         26.639546         43.441815    {"gbr": 0.3330259578223672, "rf": 0.3330179476158209, "ridge": 0.3339560945618119}     {"ensemble": 0.7913759499261196, "minutes": 0.0767387096369512, "prior": 0.13188534043692918}
2024-25                        proxy_history              19590   7984 7.678893 10.014196               -0.375627         25.187876         42.021543  {"gbr": 0.33342520866213043, "rf": 0.33355093365235294, "ridge": 0.3330238576855165}   {"ensemble": 0.9130129404027366, "minutes": 6.26792352666062e-17, "prior": 0.08698705959726331}
2024-25 official_history_with_proxy_fallback              19590   7984 7.674660 10.006336               -0.366057         25.313126         41.958918 {"gbr": 0.33379245445524397, "rf": 0.33334088312542937, "ridge": 0.33286666241932666}  {"ensemble": 0.9121271210000045, "minutes": 5.333073062896266e-17, "prior": 0.08787287899999557}
2025-26                        proxy_history              18412   7407 7.557599  9.831955               -0.162804         25.651411         42.284326   {"gbr": 0.33315184739367315, "rf": 0.3331655516838789, "ridge": 0.3336826009224479}                    {"ensemble": 0.8673111869302464, "minutes": 0.0, "prior": 0.13268881306975344}
2025-26 official_history_with_proxy_fallback              18412   7407 7.552247  9.827158               -0.170530         25.543405         42.392332   {"gbr": 0.3334811229537382, "rf": 0.33308001996446396, "ridge": 0.3334388570817978}                    {"ensemble": 0.8567418398515284, "minutes": 0.0, "prior": 0.14325816014847162}

## Paired validation bootstrap

- Validation seasons: 2021-22, 2022-23, 2023-24, 2024-25.
- Paired validation rows: 30,971.
- Macro-season delta MAE (official-history minus proxy-history): -0.0031.
- 95% date-cluster bootstrap interval: [-0.0079, 0.0014].
- Bootstrap fraction favoring official history: 0.9112.
- Secondary 2025/26 delta MAE: -0.0053518799750298905.

## Decision

Promote official PDK history only if the validation-season improvement is consistent and the confidence interval supports it. The 2025/26 secondary fold is not used to choose the change, and the frozen 2026/27 GW1 run remains untouched.

## Limitations

- This is a within-season temporal OOF ablation, not a project-wide untouched season holdout.
- 2025/26 is descriptive only and excluded from validation feature-selection bootstrap because it has already been inspected by other experiments.
- The internal OOF trainer has fold-local model weights, but its own Ridge tuning protocol and projection calibration are part of the production code under test.
- Game-level metrics do not establish better lineup, coach, injury, or transfer-malus decisions.

## Artifacts

- Metrics: reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason_metrics.csv
- Predictions: reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason_predictions.csv
- Audit JSON: reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason.json
