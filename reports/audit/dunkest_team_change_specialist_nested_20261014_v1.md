# Nested team-change specialist — V1

Generated UTC: 2026-10-14T20:26:28.746570+00:00

## Method

An expanded-lag HGB model is compared with a rotation-aware HGB model. For each outer held-out season, the blend weight is chosen only on a later-in-time validation slice within the training block and only among player-games with an as-of observed team change. The rotation model is used only for the team-change subgroup; all other rows keep the expanded-lag forecast. Rookie labels are descriptive only. No 2025/26 holdout or 2026/27 prospective bundle is loaded.

## Pooled metrics by cohort

              candidate                cohort     n    mae    rmse  bias_pred_minus_actual
           expanded_hgb                   all 57682 7.5701  9.8312                 -0.0260
           expanded_hgb           team_change   555 7.0393  8.8106                  1.4633
           expanded_hgb         rookie_season  5540 6.4282  8.5721                 -0.6252
           expanded_hgb low_history_nonrookie   338 4.9477  6.7997                  0.4023
           expanded_hgb        stable_veteran 43545 7.9896 10.2706                  0.0096
           rotation_hgb                   all 57682 7.5701  9.8312                 -0.0260
           rotation_hgb           team_change   555 7.0393  8.8106                  1.4633
           rotation_hgb         rookie_season  5540 6.4282  8.5721                 -0.6252
           rotation_hgb low_history_nonrookie   338 4.9477  6.7997                  0.4023
           rotation_hgb        stable_veteran 43545 7.9896 10.2706                  0.0096
nested_team_change_gate                   all 57682 7.5701  9.8312                 -0.0260
nested_team_change_gate           team_change   555 7.0393  8.8106                  1.4633
nested_team_change_gate         rookie_season  5540 6.4282  8.5721                 -0.6252
nested_team_change_gate low_history_nonrookie   338 4.9477  6.7997                  0.4023
nested_team_change_gate        stable_veteran 43545 7.9896 10.2706                  0.0096

## Fold metrics

fold_season_id fold_season               candidate                cohort     n    mae    rmse  bias_pred_minus_actual
             9     2022-23            expanded_hgb                   all 19165 7.5664  9.8252                 -0.0947
             9     2022-23            expanded_hgb           team_change   161 7.1233  8.6933                  1.2931
             9     2022-23            expanded_hgb         rookie_season  1637 6.6312  8.6527                 -0.8052
             9     2022-23            expanded_hgb low_history_nonrookie   123 5.1832  7.5224                 -0.4794
             9     2022-23            expanded_hgb        stable_veteran 14745 7.9524 10.2502                 -0.0783
             9     2022-23            rotation_hgb                   all 19165 7.5664  9.8252                 -0.0947
             9     2022-23            rotation_hgb           team_change   161 7.1233  8.6933                  1.2931
             9     2022-23            rotation_hgb         rookie_season  1637 6.6312  8.6527                 -0.8052
             9     2022-23            rotation_hgb low_history_nonrookie   123 5.1832  7.5224                 -0.4794
             9     2022-23            rotation_hgb        stable_veteran 14745 7.9524 10.2502                 -0.0783
             9     2022-23 nested_team_change_gate                   all 19165 7.5664  9.8252                 -0.0947
             9     2022-23 nested_team_change_gate           team_change   161 7.1233  8.6933                  1.2931
             9     2022-23 nested_team_change_gate         rookie_season  1637 6.6312  8.6527                 -0.8052
             9     2022-23 nested_team_change_gate low_history_nonrookie   123 5.1832  7.5224                 -0.4794
             9     2022-23 nested_team_change_gate        stable_veteran 14745 7.9524 10.2502                 -0.0783
            13     2023-24            expanded_hgb                   all 18927 7.5724  9.8015                  0.0894
            13     2023-24            expanded_hgb           team_change   207 7.2226  8.9554                  1.2829
            13     2023-24            expanded_hgb         rookie_season  1810 6.5533  8.7581                 -0.5643
            13     2023-24            expanded_hgb low_history_nonrookie   139 4.9297  6.5927                  1.0674
            13     2023-24            expanded_hgb        stable_veteran 14552 7.9612 10.2028                  0.1145
            13     2023-24            rotation_hgb                   all 18927 7.5724  9.8015                  0.0894
            13     2023-24            rotation_hgb           team_change   207 7.2226  8.9554                  1.2829
            13     2023-24            rotation_hgb         rookie_season  1810 6.5533  8.7581                 -0.5643
            13     2023-24            rotation_hgb low_history_nonrookie   139 4.9297  6.5927                  1.0674
            13     2023-24            rotation_hgb        stable_veteran 14552 7.9612 10.2028                  0.1145
            13     2023-24 nested_team_change_gate                   all 18927 7.5724  9.8015                  0.0894
            13     2023-24 nested_team_change_gate           team_change   207 7.2226  8.9554                  1.2829
            13     2023-24 nested_team_change_gate         rookie_season  1810 6.5533  8.7581                 -0.5643
            13     2023-24 nested_team_change_gate low_history_nonrookie   139 4.9297  6.5927                  1.0674
            13     2023-24 nested_team_change_gate        stable_veteran 14552 7.9612 10.2028                  0.1145
            19     2024-25            expanded_hgb                   all 19590 7.5715  9.8657                 -0.0704
            19     2024-25            expanded_hgb           team_change   187 6.7642  8.7490                  1.8094
            19     2024-25            expanded_hgb         rookie_season  2093 6.1614  8.3430                 -0.5370
            19     2024-25            expanded_hgb low_history_nonrookie    76 4.5995  5.8784                  0.6127
            19     2024-25            expanded_hgb        stable_veteran 14248 8.0570 10.3604                 -0.0067
            19     2024-25            rotation_hgb                   all 19590 7.5715  9.8657                 -0.0704
            19     2024-25            rotation_hgb           team_change   187 6.7642  8.7490                  1.8094
            19     2024-25            rotation_hgb         rookie_season  2093 6.1614  8.3430                 -0.5370
            19     2024-25            rotation_hgb low_history_nonrookie    76 4.5995  5.8784                  0.6127
            19     2024-25            rotation_hgb        stable_veteran 14248 8.0570 10.3604                 -0.0067
            19     2024-25 nested_team_change_gate                   all 19590 7.5715  9.8657                 -0.0704
            19     2024-25 nested_team_change_gate           team_change   187 6.7642  8.7490                  1.8094
            19     2024-25 nested_team_change_gate         rookie_season  2093 6.1614  8.3430                 -0.5370
            19     2024-25 nested_team_change_gate low_history_nonrookie    76 4.5995  5.8784                  0.6127
            19     2024-25 nested_team_change_gate        stable_veteran 14248 8.0570 10.3604                 -0.0067

## Fold-specific selection

[
  {
    "season": "2022-23",
    "outer_train_rows": 36071,
    "outer_test_rows": 19165,
    "inner_train_rows": 29177,
    "inner_valid_rows": 6894,
    "inner_cutoff": "2022-02-02T00:00:00",
    "inner_team_change_rows": 74,
    "inner_scores": [
      {
        "rotation_weight": 0.0,
        "n_team_change": 74,
        "mae": 5.929856212487424,
        "rmse": 7.625174271239958
      },
      {
        "rotation_weight": 0.25,
        "n_team_change": 74,
        "mae": 5.929856212487424,
        "rmse": 7.625174271239958
      },
      {
        "rotation_weight": 0.5,
        "n_team_change": 74,
        "mae": 5.929856212487424,
        "rmse": 7.625174271239958
      },
      {
        "rotation_weight": 0.75,
        "n_team_change": 74,
        "mae": 5.929856212487424,
        "rmse": 7.625174271239958
      },
      {
        "rotation_weight": 1.0,
        "n_team_change": 74,
        "mae": 5.929856212487424,
        "rmse": 7.625174271239958
      }
    ],
    "selected_rotation_weight": 0.0,
    "outer_team_change_rows": 161
  },
  {
    "season": "2023-24",
    "outer_train_rows": 55236,
    "outer_test_rows": 18927,
    "inner_train_rows": 44533,
    "inner_valid_rows": 10703,
    "inner_cutoff": "2022-12-30T00:00:00",
    "inner_team_change_rows": 79,
    "inner_scores": [
      {
        "rotation_weight": 0.0,
        "n_team_change": 79,
        "mae": 6.679633459800738,
        "rmse": 8.755763678962321
      },
      {
        "rotation_weight": 0.25,
        "n_team_change": 79,
        "mae": 6.679633459800738,
        "rmse": 8.755763678962321
      },
      {
        "rotation_weight": 0.5,
        "n_team_change": 79,
        "mae": 6.679633459800738,
        "rmse": 8.755763678962321
      },
      {
        "rotation_weight": 0.75,
        "n_team_change": 79,
        "mae": 6.679633459800738,
        "rmse": 8.755763678962321
      },
      {
        "rotation_weight": 1.0,
        "n_team_change": 79,
        "mae": 6.679633459800738,
        "rmse": 8.755763678962321
      }
    ],
    "selected_rotation_weight": 0.0,
    "outer_team_change_rows": 207
  },
  {
    "season": "2024-25",
    "outer_train_rows": 74163,
    "outer_test_rows": 19590,
    "inner_train_rows": 58587,
    "inner_valid_rows": 15576,
    "inner_cutoff": "2023-11-24T00:00:00",
    "inner_team_change_rows": 100,
    "inner_scores": [
      {
        "rotation_weight": 0.0,
        "n_team_change": 100,
        "mae": 7.012305630936155,
        "rmse": 8.608952592803709
      },
      {
        "rotation_weight": 0.25,
        "n_team_change": 100,
        "mae": 7.012305630936155,
        "rmse": 8.608952592803709
      },
      {
        "rotation_weight": 0.5,
        "n_team_change": 100,
        "mae": 7.012305630936155,
        "rmse": 8.608952592803709
      },
      {
        "rotation_weight": 0.75,
        "n_team_change": 100,
        "mae": 7.012305630936155,
        "rmse": 8.608952592803709
      },
      {
        "rotation_weight": 1.0,
        "n_team_change": 100,
        "mae": 7.012305630936155,
        "rmse": 8.608952592803709
      }
    ],
    "selected_rotation_weight": 0.0,
    "outer_team_change_rows": 187
  }
]

## Decision

Promote only if the nested gate improves team-change MAE without a material total MAE/RMSE penalty and the direction is stable in every outer season. Team-change labels are derived from the prior observed team in the linked archive, not an independently verified transaction feed. This is player-level PDK validation only. No production changes or commits/pushes.
