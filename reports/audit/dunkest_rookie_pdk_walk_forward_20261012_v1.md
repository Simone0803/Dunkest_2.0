# Rookie-specific official PDK walk-forward validation

Created: 2026-10-12T17:20:08.037016+00:00

## Method

- Draft-year cohorts are matched by normalized player name to the NBA season immediately after the draft. This approximates the typical rookie season but is not a verified debut-season label for players with delayed NBA debuts.
- For each test season, the Random Forest is trained only on verified official PDK rows from strictly earlier seasons.
- 2025/26 also uses the existing fixed holdout trained on 2020/21–2024/25; its predictions match the walk-forward fit for that season.
- Target is `target_pdk` from the verified training dataset. No reconstructed or synthetic targets are created.
- Results are separated into all rookie games, first three Dunkest games, and rows with/without prior official PDK history.
- The 2020/21 cohort is not scored because there is no earlier verified training season in the current dataset.

## Cohort coverage

| season  | draft_year | rookie_players_matched | rookie_rows | train_seasons                           | status                                       | rookie_players_in_source |
| ------- | ---------- | ---------------------- | ----------- | --------------------------------------- | -------------------------------------------- | ------------------------ |
| 2020-21 | 2020       | 47                     | 1491        |                                         | skipped: no earlier verified training season | 48                       |
| 2021-22 | 2021       | 42                     | 1396        | 2020-21                                 | evaluated                                    | 48                       |
| 2022-23 | 2022       | 41                     | 1416        | 2020-21;2021-22                         | evaluated                                    | 43                       |
| 2023-24 | 2023       | 44                     | 1241        | 2020-21;2021-22;2022-23                 | evaluated                                    | 45                       |
| 2024-25 | 2024       | 41                     | 1490        | 2020-21;2021-22;2022-23;2023-24         | evaluated                                    | 42                       |
| 2025-26 | 2025       | 42                     | 1676        | 2020-21;2021-22;2022-23;2023-24;2024-25 | evaluated                                    | 44                       |

### Unmatched rookie names

- **2020-21**: Aaron Nesmith, Anthony Edwards, CJ Elleby, Cassius Stanley, Cassius Winston, Cole Anthony, Daniel Oturu, Desmond Bane, Devin Vassell, Elijah Hughes, Grant Riller, Immanuel Quickley, Isaac Okoro, Isaiah Joe, Isaiah Stewart, Jaden McDaniels, Jahmi'us Ramsey, Jalen Harris, Jalen Smith, James Wiseman, Jordan Nwora, Josh Green, Justinian Jessup, Kira Lewis Jr., Malachi Flynn, Nick Richards, Nico Mannion, Obi Toppin, Onyeka Okongwu, Patrick Williams, Paul Reed, Payton Pritchard, Precious Achiuwa, Reggie Perry, Robert Woodard II, Saben Lee, Saddiq Bey, Sam Merrill, Skylar Mays, Tre Jones, Tyler Bey, Tyrell Terry, Tyrese Haliburton, Tyrese Maxey, Udoka Azubuike, Vernon Carey Jr., Xavier Tillman, Zeke Nnaji
- **2021-22**: Balsa Koprivica, Brandon Boston, Greg Brown III, Jason Preston, Marcus Zegarowski, RaiQuan Gray
- **2022-23**: Chet Holmgren, E.J. Liddell
- **2023-24**: Jaylen Clark
- **2024-25**: DaRon Holmes II
- **2025-26**: Johni Broome, Thomas Sorber

## Weighted metrics across evaluated seasons

| segment                      | model                        | n    | weighted_mae      | weighted_rmse      |
| ---------------------------- | ---------------------------- | ---- | ----------------- | ------------------ |
| all_rookie_games             | baseline_prev10_walk_forward | 7219 | 6.714224261043937 | 8.899048232739712  |
| all_rookie_games             | random_forest_walk_forward   | 7219 | 6.431105388466911 | 8.502611667516929  |
| first_3_dunkest_games        | baseline_prev10_walk_forward | 623  | 6.772953451043339 | 8.723941495487772  |
| first_3_dunkest_games        | random_forest_walk_forward   | 623  | 4.887303763478317 | 6.926273737343516  |
| no_prior_official_pdk        | baseline_prev10_walk_forward | 210  | 9.58947619047619  | 10.444779990388453 |
| no_prior_official_pdk        | random_forest_walk_forward   | 210  | 5.139842265665697 | 7.528458011613019  |
| prior_official_pdk_available | baseline_prev10_walk_forward | 7009 | 6.628077463329462 | 8.848570516174806  |
| prior_official_pdk_available | random_forest_walk_forward   | 7009 | 6.469793540241524 | 8.530082375730247  |

## Per-season metrics

| season  | model                                 | segment                      | n    | mae                | rmse               | bias_pred_minus_actual | r2                  |
| ------- | ------------------------------------- | ---------------------------- | ---- | ------------------ | ------------------ | ---------------------- | ------------------- |
| 2021-22 | random_forest_walk_forward            | all_rookie_games             | 1396 | 6.768534051535272  | 8.87692823879201   | 0.0903137957958728     | 0.2986310776036893  |
| 2021-22 | random_forest_walk_forward            | no_prior_official_pdk        | 42   | 4.152089573141825  | 6.813845164880821  | -0.7741698730760215    | 0.0073866003642846  |
| 2021-22 | random_forest_walk_forward            | prior_official_pdk_available | 1354 | 6.849694072283075  | 8.933307842185348  | 0.1171293896604365     | 0.297234475959977   |
| 2021-22 | random_forest_walk_forward            | first_3_dunkest_games        | 123  | 4.65220672079344   | 7.088515066568415  | 0.2387677648358034     | 0.1241523867883011  |
| 2021-22 | baseline_prev10_walk_forward          | all_rookie_games             | 1396 | 7.036840945786145  | 9.304933432596236  | -0.6108251466775821    | 0.2293669308255549  |
| 2021-22 | baseline_prev10_walk_forward          | no_prior_official_pdk        | 42   | 8.851190476190476  | 9.680537052201576  | 6.851190476190476      | -1.0035238446569288 |
| 2021-22 | baseline_prev10_walk_forward          | prior_official_pdk_available | 1354 | 6.980561270544655  | 9.293039755554714  | -0.8422909193219384    | 0.2394961133046143  |
| 2021-22 | baseline_prev10_walk_forward          | first_3_dunkest_games        | 123  | 6.8861788617886175 | 9.114727205600852  | 2.3353658536585367     | -0.4481227209097349 |
| 2022-23 | random_forest_walk_forward            | all_rookie_games             | 1416 | 6.497084880988317  | 8.506357361606534  | -0.3433880714428782    | 0.3428745935474795  |
| 2022-23 | random_forest_walk_forward            | no_prior_official_pdk        | 41   | 6.790896658797645  | 9.732295886282996  | -3.1613190008027603    | -0.131624142536529  |
| 2022-23 | random_forest_walk_forward            | prior_official_pdk_available | 1375 | 6.488323947977277  | 8.467077234292185  | -0.2593624946401471    | 0.3505674680711131  |
| 2022-23 | random_forest_walk_forward            | first_3_dunkest_games        | 123  | 5.235331709311134  | 7.524679123741879  | -0.6699226680868411    | 0.215155653232881   |
| 2022-23 | baseline_prev10_walk_forward          | all_rookie_games             | 1416 | 6.7029779840373065 | 8.740240873139362  | -0.4293544132813199    | 0.3062423040305696  |
| 2022-23 | baseline_prev10_walk_forward          | no_prior_official_pdk        | 41   | 9.21951219512195   | 10.200356282634589 | 4.510731707317073      | -0.243089157942111  |
| 2022-23 | baseline_prev10_walk_forward          | prior_official_pdk_available | 1375 | 6.62793950937951   | 8.692938228952267  | -0.5766587994227993    | 0.3154578658960368  |
| 2022-23 | baseline_prev10_walk_forward          | first_3_dunkest_games        | 123  | 6.526341463414634  | 8.238610270366712  | 1.736829268292683      | 0.0591606302189706  |
| 2023-24 | random_forest_walk_forward            | all_rookie_games             | 1241 | 6.0101040164718915 | 7.967888858062517  | 0.087930794632308      | 0.2954625123249412  |
| 2023-24 | random_forest_walk_forward            | no_prior_official_pdk        | 44   | 5.267365575220165  | 7.088855262568362  | 0.8167927212860288     | -0.006832106828845  |
| 2023-24 | random_forest_walk_forward            | prior_official_pdk_available | 1197 | 6.037406014312388  | 7.998360241268368  | 0.0611388775289131     | 0.29237931827754    |
| 2023-24 | random_forest_walk_forward            | first_3_dunkest_games        | 128  | 4.72835450003296   | 6.282751068783035  | 0.4578513296562526     | 0.0963346494914977  |
| 2023-24 | baseline_prev10_walk_forward          | all_rookie_games             | 1241 | 6.292525501068007  | 8.425676455468318  | -0.2227385461033728    | 0.2121797715841742  |
| 2023-24 | baseline_prev10_walk_forward          | no_prior_official_pdk        | 44   | 10.45909090909091  | 11.308038974753556 | 8.829545454545455      | -1.562001804348573  |
| 2023-24 | baseline_prev10_walk_forward          | prior_official_pdk_available | 1197 | 6.139368543713782  | 8.300675086621084  | -0.5554874985081752    | 0.2378763730260591  |
| 2023-24 | baseline_prev10_walk_forward          | first_3_dunkest_games        | 128  | 6.8944140625       | 8.739692980788142  | 2.2829296875           | -0.7486394732357586 |
| 2024-25 | random_forest_walk_forward            | all_rookie_games             | 1490 | 6.284053235717108  | 8.417370021542716  | -0.4562678238481875    | 0.2961602985359356  |
| 2024-25 | random_forest_walk_forward            | no_prior_official_pdk        | 41   | 4.156774371390716  | 5.54081920710337   | 1.0574845195286338     | -0.0869687731279189 |
| 2024-25 | random_forest_walk_forward            | prior_official_pdk_available | 1449 | 6.344245391298462  | 8.48458709619891   | -0.4991000157587808    | 0.2884763081670922  |
| 2024-25 | random_forest_walk_forward            | first_3_dunkest_games        | 123  | 4.598174498761055  | 6.1591386025692625 | 0.0549469857283652     | 0.0862866307513213  |
| 2024-25 | baseline_prev10_walk_forward          | all_rookie_games             | 1490 | 6.700012426760414  | 8.946826110460506  | -0.7900160274848196    | 0.204831960930256   |
| 2024-25 | baseline_prev10_walk_forward          | no_prior_official_pdk        | 41   | 9.94780487804878   | 10.79155383373226  | 9.39219512195122       | -3.1232253512306185 |
| 2024-25 | baseline_prev10_walk_forward          | prior_official_pdk_available | 1449 | 6.608114917786761  | 8.889061143152697  | -1.078125521706267     | 0.2190203309950199  |
| 2024-25 | baseline_prev10_walk_forward          | first_3_dunkest_games        | 123  | 6.802764227642276  | 8.644753378530226  | 1.7005691056910568     | -0.8000113384699552 |
| 2025-26 | random_forest_walk_forward            | all_rookie_games             | 1676 | 6.536769490608489  | 8.638603381993256  | -0.2415653104118928    | 0.3363388579366498  |
| 2025-26 | random_forest_walk_forward            | no_prior_official_pdk        | 42   | 5.3419170516769    | 7.866574064941145  | -2.189639271819231     | -0.0741636282318354 |
| 2025-26 | random_forest_walk_forward            | prior_official_pdk_available | 1634 | 6.567481732000856  | 8.657539979664142  | -0.1914924178910187    | 0.3371714354014133  |
| 2025-26 | random_forest_walk_forward            | first_3_dunkest_games        | 126  | 5.220779193589685  | 7.466357765742027  | -0.4836089685267468    | 0.2091540395942079  |
| 2025-26 | baseline_prev10_walk_forward          | all_rookie_games             | 1676 | 6.779889911732394  | 8.984424612487313  | -0.5281672491192181    | 0.2821398293254021  |
| 2025-26 | baseline_prev10_walk_forward          | no_prior_official_pdk        | 42   | 9.428095238095237  | 10.126138736669851 | 6.702857142857143      | -0.7798644037151459 |
| 2025-26 | baseline_prev10_walk_forward          | prior_official_pdk_available | 1634 | 6.711820986574965  | 8.953159200326263  | -0.7140320131724661    | 0.2911329029937326  |
| 2025-26 | baseline_prev10_walk_forward          | first_3_dunkest_games        | 126  | 6.750674603174604  | 8.854472560542316  | 1.6471031746031746     | -0.1122430510269194 |
| 2025-26 | random_forest_fixed_2020_25_holdout   | all_rookie_games             | 1676 | 6.536769490608489  | 8.638603381993256  | -0.2415653104118927    | 0.3363388579366498  |
| 2025-26 | random_forest_fixed_2020_25_holdout   | first_3_dunkest_games        | 126  | 5.220779193589685  | 7.466357765742027  | -0.483608968526747     | 0.2091540395942079  |
| 2025-26 | baseline_prev10_fixed_2020_25_holdout | all_rookie_games             | 1676 | 6.779889911732394  | 8.984424612487313  | -0.528167249119218     | 0.2821398293254021  |
| 2025-26 | baseline_prev10_fixed_2020_25_holdout | first_3_dunkest_games        | 126  | 6.750674603174604  | 8.854472560542316  | 1.6471031746031746     | -0.1122430510269194 |

## Interpretation

Across the evaluated 2021/22–2025/26 cohorts (7,219 official rookie player-game rows), the Random Forest reduces weighted MAE from 6.714 to 6.431 PDK versus the previous-10 PDK mean baseline (about 4.2%). On the first three Dunkest games per matched rookie, weighted MAE is 4.887 versus 6.773 (about 27.8% lower). The no-prior-official-PDK segment has 210 rows and MAE 5.140 versus 9.590 for the baseline; this segment is small, and the metric must not be interpreted as a probability-of-playing model.

These are game-score prediction metrics conditional on an official target row existing. The cohort is defined by draft year and the following NBA season, so players with delayed NBA debuts may be missed or misclassified; a verified NBA player-ID/debut crosswalk is needed for an exact rookie-season analysis. The current data does not reliably distinguish DNP / zero-minute outcomes from missing data, so this audit does not estimate participation probability and does not fabricate zero labels. The first-three-games slice is useful for early-season performance forecasting but does not independently validate the college minutes prior.

## Artifacts

- Per-game predictions: `reports/audit/dunkest_rookie_pdk_walk_forward_predictions_20261012_v1.csv`
- Metrics: `reports/audit/dunkest_rookie_pdk_walk_forward_metrics_20261012_v1.csv`
- Audit JSON: `reports/audit/dunkest_rookie_pdk_walk_forward_audit_20261012_v1.json`
