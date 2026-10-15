# Role / rotation cohort audit — V1

Generated UTC: 2026-10-14T20:20:10.016287+00:00

## Design

Reuses the same outer-fold predictions from the PDK lag-feature ablation; no models were retrained and no 2025/26 holdout or 2026/27 prospective data was loaded. Cohort tags use player history/team metadata and are diagnostics, not model inputs. Team change is detected when the target team differs from the previous observed team for that NBA player on an earlier target date. Rookie-season classification requires a row with zero cumulative prior NBA games and marks that player-season; low-history non-rookies are separately defined as fewer than five prior Dunkest games without the rookie-season tag.

## Feature impact: expanded lags minus adapter feature set

Negative delta MAE means expanded lags help.

model                  cohort     n  players  mae_adapter  mae_expanded  delta_mae_expanded_minus_adapter  bias_adapter  bias_expanded
 et12                     all 57682      671       7.6042        7.5696                           -0.0346       -0.3700        -0.1279
 et12           rookie_season     0        0          NaN           NaN                               NaN           NaN            NaN
 et12   low_history_nonrookie  1222      252       5.2012        5.1388                           -0.0624        0.2312        -0.1339
 et12 experienced_team_change   555      349       7.2986        7.3598                            0.0612        1.7635         2.0985
 et12          stable_veteran 43545      471       7.9907        7.9754                           -0.0153       -0.5961        -0.1957
  hgb                     all 57682      671       7.5810        7.5721                           -0.0089       -0.4366         0.0275
  hgb           rookie_season     0        0          NaN           NaN                               NaN           NaN            NaN
  hgb   low_history_nonrookie  1222      252       5.2469        5.1747                           -0.0722        0.4557        -0.0029
  hgb experienced_team_change   555      349       7.0149        7.0630                            0.0481        0.9127         1.5171
  hgb          stable_veteran 43545      471       7.9681        7.9960                            0.0279       -0.6917         0.0802

## Metrics by model and cohort

model      feature_set                  cohort     n    mae    rmse  bias_pred_minus_actual  unique_players
  hgb adapter_features                     all 57682 7.5810  9.8833                 -0.4366             NaN
  hgb adapter_features   low_history_nonrookie  1222 5.2469  7.0434                  0.4557        252.0000
  hgb adapter_features experienced_team_change   555 7.0149  8.8369                  0.9127        349.0000
  hgb adapter_features          stable_veteran 43545 7.9681 10.3260                 -0.6917        471.0000
  hgb    expanded_lags                     all 57682 7.5721  9.8304                  0.0275             NaN
  hgb    expanded_lags   low_history_nonrookie  1222 5.1747  7.0366                 -0.0029        252.0000
  hgb    expanded_lags experienced_team_change   555 7.0630  8.9000                  1.5171        349.0000
  hgb    expanded_lags          stable_veteran 43545 7.9960 10.2731                  0.0802        471.0000
 et12 adapter_features                     all 57682 7.6042  9.9073                 -0.3700             NaN
 et12 adapter_features   low_history_nonrookie  1222 5.2012  7.0575                  0.2312        252.0000
 et12 adapter_features experienced_team_change   555 7.2986  9.0973                  1.7635        349.0000
 et12 adapter_features          stable_veteran 43545 7.9907 10.3471                 -0.5961        471.0000
 et12    expanded_lags                     all 57682 7.5696  9.8458                 -0.1279             NaN
 et12    expanded_lags   low_history_nonrookie  1222 5.1388  7.0400                 -0.1339        252.0000
 et12    expanded_lags experienced_team_change   555 7.3598  9.1256                  2.0985        349.0000
 et12    expanded_lags          stable_veteran 43545 7.9754 10.2872                 -0.1957        471.0000

## Per-season cohort metrics

model      feature_set                  cohort season_id     n    mae    rmse  bias_pred_minus_actual  unique_players
  hgb adapter_features                     all        13 18927 7.5625  9.8467                 -0.3884             512
  hgb adapter_features                     all        19 19590 7.5947  9.9056                 -0.3802             509
  hgb adapter_features                     all         9 19165 7.5854  9.8966                 -0.5420             482
  hgb adapter_features   low_history_nonrookie        13   434 5.4513  7.2733                  0.5147              93
  hgb adapter_features   low_history_nonrookie        19   404 4.7194  6.2627                  0.5964              85
  hgb adapter_features   low_history_nonrookie         9   384 5.5710  7.5379                  0.2411              81
  hgb adapter_features experienced_team_change        13   207 7.1259  8.9361                  0.6136             170
  hgb adapter_features experienced_team_change        19   187 6.6236  8.5854                  1.2048             158
  hgb adapter_features experienced_team_change         9   161 7.3266  8.9952                  0.9581             143
  hgb adapter_features          stable_veteran        13 14552 7.9158 10.2477                 -0.6506             361
  hgb adapter_features          stable_veteran        19 14248 8.0563 10.4076                 -0.5994             367
  hgb adapter_features          stable_veteran         9 14745 7.9344 10.3239                 -0.8216             363
  hgb    expanded_lags                     all        13 18927 7.5726  9.8055                  0.1331             512
  hgb    expanded_lags                     all        19 19590 7.5646  9.8563                 -0.0708             509
  hgb    expanded_lags                     all         9 19165 7.5792  9.8284                  0.0238             482
  hgb    expanded_lags   low_history_nonrookie        13   434 5.3670  7.2872                 -0.0836              93
  hgb    expanded_lags   low_history_nonrookie        19   404 4.7301  6.2847                  0.3550              85
  hgb    expanded_lags   low_history_nonrookie         9   384 5.4250  7.4830                 -0.2881              81
  hgb    expanded_lags experienced_team_change        13   207 7.1980  9.0274                  1.2234             170
  hgb    expanded_lags experienced_team_change        19   187 6.7138  8.7564                  1.9028             158
  hgb    expanded_lags experienced_team_change         9   161 7.2949  8.9005                  1.4468             143
  hgb    expanded_lags          stable_veteran        13 14552 7.9676 10.2084                  0.1816             361
  hgb    expanded_lags          stable_veteran        19 14248 8.0561 10.3560                 -0.0075             367
  hgb    expanded_lags          stable_veteran         9 14745 7.9658 10.2562                  0.0649             363
 et12 adapter_features                     all        13 18927 7.5934  9.8758                 -0.3319             512
 et12 adapter_features                     all        19 19590 7.6208  9.9311                 -0.3172             509
 et12 adapter_features                     all         9 19165 7.5980  9.9140                 -0.4617             482
 et12 adapter_features   low_history_nonrookie        13   434 5.3997  7.2794                  0.3195              93
 et12 adapter_features   low_history_nonrookie        19   404 4.7029  6.2483                  0.4832              85
 et12 adapter_features   low_history_nonrookie         9   384 5.5012  7.5855                 -0.1337              81
 et12 adapter_features experienced_team_change        13   207 7.4342  9.0875                  1.4535             170
 et12 adapter_features experienced_team_change        19   187 7.0678  9.1422                  2.3678             158
 et12 adapter_features experienced_team_change         9   161 7.3923  9.0575                  1.4603             143
 et12 adapter_features          stable_veteran        13 14552 7.9488 10.2831                 -0.5757             361
 et12 adapter_features          stable_veteran        19 14248 8.0764 10.4244                 -0.5120             367
 et12 adapter_features          stable_veteran         9 14745 7.9492 10.3349                 -0.6975             363
 et12    expanded_lags                     all        13 18927 7.5687  9.8191                 -0.0539             512
 et12    expanded_lags                     all        19 19590 7.5763  9.8772                 -0.1279             509
 et12    expanded_lags                     all         9 19165 7.5637  9.8401                 -0.2010             482
 et12    expanded_lags   low_history_nonrookie        13   434 5.3524  7.2526                 -0.0607              93
 et12    expanded_lags   low_history_nonrookie        19   404 4.6901  6.2905                  0.2289              85
 et12    expanded_lags   low_history_nonrookie         9   384 5.3693  7.5261                 -0.5984              81
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
