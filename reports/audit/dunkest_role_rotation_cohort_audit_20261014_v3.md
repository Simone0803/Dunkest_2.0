# Role / rotation cohort audit — V1

Generated UTC: 2026-10-14T20:21:31.278912+00:00

## Design

Reuses the same outer-fold predictions from the PDK lag-feature ablation; no models were retrained and no 2025/26 holdout or 2026/27 prospective data was loaded. Cohort tags use player history/team metadata and are diagnostics, not model inputs. Team change is detected when the target team differs from the previous observed team for that NBA player on an earlier target date. Rookie-season classification requires a row with no archived prior NBA game date and marks that player-season; low-history non-rookies are separately defined as fewer than five prior Dunkest games without the rookie-season tag.

## Feature impact: expanded lags minus adapter feature set

Negative delta MAE means expanded lags help.

model                  cohort     n  players  mae_adapter  mae_expanded  delta_mae_expanded_minus_adapter  bias_adapter  bias_expanded
 et12                     all 57682      671       7.6042        7.5696                           -0.0346       -0.3700        -0.1279
 et12           rookie_season  5540      182       6.4956        6.4244                           -0.0712       -0.0354        -0.4311
 et12   low_history_nonrookie   338       73       5.1027        4.9298                           -0.1729        0.8472         0.4167
 et12 experienced_team_change   555      349       7.2986        7.3598                            0.0612        1.7635         2.0985
 et12          stable_veteran 43545      471       7.9907        7.9754                           -0.0153       -0.5961        -0.1957
  hgb                     all 57682      671       7.5810        7.5721                           -0.0089       -0.4366         0.0275
  hgb           rookie_season  5540      182       6.4962        6.4073                           -0.0889        0.0484        -0.6564
  hgb   low_history_nonrookie   338       73       5.1061        4.8664                           -0.2397        0.9434         0.3663
  hgb experienced_team_change   555      349       7.0149        7.0630                            0.0481        0.9127         1.5171
  hgb          stable_veteran 43545      471       7.9681        7.9960                            0.0279       -0.6917         0.0802

## Metrics by model and cohort

model      feature_set                  cohort     n    mae    rmse  bias_pred_minus_actual  unique_players
  hgb adapter_features                     all 57682 7.5810  9.8833                 -0.4366             NaN
  hgb adapter_features           rookie_season  5540 6.4962  8.5425                  0.0484        182.0000
  hgb adapter_features   low_history_nonrookie   338 5.1061  6.8711                  0.9434         73.0000
  hgb adapter_features experienced_team_change   555 7.0149  8.8369                  0.9127        349.0000
  hgb adapter_features          stable_veteran 43545 7.9681 10.3260                 -0.6917        471.0000
  hgb    expanded_lags                     all 57682 7.5721  9.8304                  0.0275             NaN
  hgb    expanded_lags           rookie_season  5540 6.4073  8.5500                 -0.6564        182.0000
  hgb    expanded_lags   low_history_nonrookie   338 4.8664  6.6888                  0.3663         73.0000
  hgb    expanded_lags experienced_team_change   555 7.0630  8.9000                  1.5171        349.0000
  hgb    expanded_lags          stable_veteran 43545 7.9960 10.2731                  0.0802        471.0000
 et12 adapter_features                     all 57682 7.6042  9.9073                 -0.3700             NaN
 et12 adapter_features           rookie_season  5540 6.4956  8.5525                 -0.0354        182.0000
 et12 adapter_features   low_history_nonrookie   338 5.1027  6.9349                  0.8472         73.0000
 et12 adapter_features experienced_team_change   555 7.2986  9.0973                  1.7635        349.0000
 et12 adapter_features          stable_veteran 43545 7.9907 10.3471                 -0.5961        471.0000
 et12    expanded_lags                     all 57682 7.5696  9.8458                 -0.1279             NaN
 et12    expanded_lags           rookie_season  5540 6.4244  8.5357                 -0.4311        182.0000
 et12    expanded_lags   low_history_nonrookie   338 4.9298  6.7509                  0.4167         73.0000
 et12    expanded_lags experienced_team_change   555 7.3598  9.1256                  2.0985        349.0000
 et12    expanded_lags          stable_veteran 43545 7.9754 10.2872                 -0.1957        471.0000

## Per-season cohort metrics

model      feature_set                  cohort season_id     n    mae    rmse  bias_pred_minus_actual  unique_players
  hgb adapter_features                     all        13 18927 7.5625  9.8467                 -0.3884             512
  hgb adapter_features                     all        19 19590 7.5947  9.9056                 -0.3802             509
  hgb adapter_features                     all         9 19165 7.5854  9.8966                 -0.5420             482
  hgb adapter_features           rookie_season        13  1810 6.6338  8.7624                  0.1277              61
  hgb adapter_features           rookie_season        19  2093 6.1884  8.2654                  0.0406              67
  hgb adapter_features           rookie_season         9  1637 6.7375  8.6442                 -0.0292              54
  hgb adapter_features   low_history_nonrookie        13   139 5.1243  6.7016                  1.5347              32
  hgb adapter_features   low_history_nonrookie        19    76 4.4912  5.7891                  0.7831              18
  hgb adapter_features   low_history_nonrookie         9   123 5.4654  7.6338                  0.3742              27
  hgb adapter_features experienced_team_change        13   207 7.1259  8.9361                  0.6136             170
  hgb adapter_features experienced_team_change        19   187 6.6236  8.5854                  1.2048             158
  hgb adapter_features experienced_team_change         9   161 7.3266  8.9952                  0.9581             143
  hgb adapter_features          stable_veteran        13 14552 7.9158 10.2477                 -0.6506             361
  hgb adapter_features          stable_veteran        19 14248 8.0563 10.4076                 -0.5994             367
  hgb adapter_features          stable_veteran         9 14745 7.9344 10.3239                 -0.8216             363
  hgb    expanded_lags                     all        13 18927 7.5726  9.8055                  0.1331             512
  hgb    expanded_lags                     all        19 19590 7.5646  9.8563                 -0.0708             509
  hgb    expanded_lags                     all         9 19165 7.5792  9.8284                  0.0238             482
  hgb    expanded_lags           rookie_season        13  1810 6.5318  8.7626                 -0.6402              61
  hgb    expanded_lags           rookie_season        19  2093 6.1258  8.2948                 -0.5482              67
  hgb    expanded_lags           rookie_season         9  1637 6.6294  8.6330                 -0.8126              54
  hgb    expanded_lags   low_history_nonrookie        13   139 4.7616  6.3816                  0.8006              32
  hgb    expanded_lags   low_history_nonrookie        19    76 4.4489  5.6846                  0.4392              18
  hgb    expanded_lags   low_history_nonrookie         9   123 5.2429  7.5469                 -0.1694              27
  hgb    expanded_lags experienced_team_change        13   207 7.1980  9.0274                  1.2234             170
  hgb    expanded_lags experienced_team_change        19   187 6.7138  8.7564                  1.9028             158
  hgb    expanded_lags experienced_team_change         9   161 7.2949  8.9005                  1.4468             143
  hgb    expanded_lags          stable_veteran        13 14552 7.9676 10.2084                  0.1816             361
  hgb    expanded_lags          stable_veteran        19 14248 8.0561 10.3560                 -0.0075             367
  hgb    expanded_lags          stable_veteran         9 14745 7.9658 10.2562                  0.0649             363
 et12 adapter_features                     all        13 18927 7.5934  9.8758                 -0.3319             512
 et12 adapter_features                     all        19 19590 7.6208  9.9311                 -0.3172             509
 et12 adapter_features                     all         9 19165 7.5980  9.9140                 -0.4617             482
 et12 adapter_features           rookie_season        13  1810 6.6138  8.7160                  0.0615              61
 et12 adapter_features           rookie_season        19  2093 6.1992  8.3049                 -0.0487              67
 et12 adapter_features           rookie_season         9  1637 6.7438  8.6809                 -0.1257              54
 et12 adapter_features   low_history_nonrookie        13   139 5.1236  6.7767                  1.3874              32
 et12 adapter_features   low_history_nonrookie        19    76 4.5683  5.8398                  1.0042              18
 et12 adapter_features   low_history_nonrookie         9   123 5.4094  7.6935                  0.1396              27
 et12 adapter_features experienced_team_change        13   207 7.4342  9.0875                  1.4535             170
 et12 adapter_features experienced_team_change        19   187 7.0678  9.1422                  2.3678             158
 et12 adapter_features experienced_team_change         9   161 7.3923  9.0575                  1.4603             143
 et12 adapter_features          stable_veteran        13 14552 7.9488 10.2831                 -0.5757             361
 et12 adapter_features          stable_veteran        19 14248 8.0764 10.4244                 -0.5120             367
 et12 adapter_features          stable_veteran         9 14745 7.9492 10.3349                 -0.6975             363
 et12    expanded_lags                     all        13 18927 7.5687  9.8191                 -0.0539             512
 et12    expanded_lags                     all        19 19590 7.5763  9.8772                 -0.1279             509
 et12    expanded_lags                     all         9 19165 7.5637  9.8401                 -0.2010             482
 et12    expanded_lags           rookie_season        13  1810 6.5478  8.7070                 -0.3565              61
 et12    expanded_lags           rookie_season        19  2093 6.1230  8.2879                 -0.3966              67
 et12    expanded_lags           rookie_season         9  1637 6.6731  8.6559                 -0.5576              54
 et12    expanded_lags   low_history_nonrookie        13   139 4.9284  6.5238                  1.0063              32
 et12    expanded_lags   low_history_nonrookie        19    76 4.6316  5.8686                  0.6354              18
 et12    expanded_lags   low_history_nonrookie         9   123 5.1156  7.4741                 -0.3847              27
 et12    expanded_lags experienced_team_change        13   207 7.5637  9.1602                  1.9249             170
 et12    expanded_lags experienced_team_change        19   187 7.0505  9.1401                  2.6297             158
 et12    expanded_lags experienced_team_change         9   161 7.4569  9.0639                  1.7047             143
 et12    expanded_lags          stable_veteran        13 14552 7.9431 10.2273                 -0.1387             361
 et12    expanded_lags          stable_veteran        19 14248 8.0546 10.3760                 -0.1647             367
 et12    expanded_lags          stable_veteran         9 14745 7.9307 10.2599                 -0.2819             363

## Interpretation safeguards

- NBA rookie status is an archive-derived proxy and may miss players whose first observed linked game is late in a season; counts are included for review.
- Team-change flags are based on previous observed linked Dunkest/NBA team, not an independently certified transaction feed. This is a rotation-change proxy, not proof of an official trade/free-agency event.
- This audit measures PDK player-game error only and does not certify lineup outcomes.
- No production weights or features were changed by this diagnostic.

No commit or push.
