# Dunkest weekly-round quarantine/review manifest (v1)

Generated UTC: 2026-10-12T14:11:11.463571+00:00

## Policy

Only the source scope confirmed by a multi-player cross-season NBA game signature is marked for quarantine from future clean derivatives. Isolated matches are review candidates, not proven errors, and must not be dropped automatically. The raw archive is preserved unchanged.

## Confirmed quarantine scope

- `data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet`
- `data/raw/dunkest_history_v2/season_5_week_43_round_2_tot.parquet`
- Evidence: 15 players map to NBA game `0022100292` on 2021-11-27 (PHI–MIN), and match season-7 official player-game history; all 15 official rows have `gameValidForDunkest=True`.

## Other candidate scopes

- Files marked for review only: 60
- The candidate CSV reports exact player/team/boxscore-signature matches to other seasons. Isolated matches can occur coincidentally; corroborate before quarantining.

## Manifest

| File | Status | Candidate rows | Candidate seasons | Action |
|---|---|---:|---|---|
| `data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet` | confirmed_cross_season_contamination_quarantine | 15 | 2021-22 | Exclude from any clean derivative pending re-fetch/reconciliation |
| `data/raw/dunkest_history_v2/season_5_week_43_round_2_tot.parquet` | confirmed_cross_season_contamination_quarantine | 15 | 2021-22 | Exclude from any clean derivative pending re-fetch/reconciliation |
| `data/raw/dunkest_history_v2/season_13_week_12_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_12_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_17_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_17_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_18_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_18_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_19_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_19_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_20_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_20_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_21_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_21_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_35_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_13_week_35_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_19_week_22_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2020-21 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_19_week_22_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2020-21 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_19_week_44_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_19_week_44_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_22_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_22_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_23_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2021-22 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_23_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2021-22 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_34_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_34_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_40_round_3_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2021-22 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_40_round_3_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2021-22 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_48_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_48_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2019-20 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_52_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_52_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_53_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2021-22 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_53_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2021-22 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_5_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_5_week_5_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_7_week_9_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_7_week_9_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2022-23 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_10_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_10_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_15_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_15_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_1_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_1_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_20_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_20_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_27_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_27_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_2_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_2_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_34_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2018-19 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_34_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2018-19 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_39_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_39_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2024-25 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_40_round_2_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_40_round_2_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_43_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_43_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_4_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_4_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_9_round_1_avg.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |
| `data/raw/dunkest_history_v2/season_9_week_9_round_1_tot.parquet` | isolated_signature_candidate_review_only | 1 | 2023-24 | Do not exclude automatically; inspect signature candidates and corroborate with official player-game history |

Source data was read only. No source Parquet, manifest, model, production configuration, target, temporal split, or backtest was changed.

JSON: `reports/audit/dunkest_week_round_quarantine_manifest_v1.json`
CSV: `reports/audit/dunkest_week_round_quarantine_manifest_v1.csv`
