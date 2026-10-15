# Graph Report - Dunkest  (2026-10-14)

## Corpus Check
- Large corpus: 670 files · ~996,119 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 2474 nodes · 7194 edges · 165 communities (139 shown, 26 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 349 edges (avg confidence: 0.91)
- Token cost (partial): 7,880 input · 9,320 output; usage for chunks 3–11 was unavailable

## Community Hubs (Navigation)
- Paired Game Cluster Bootstrap Monte
- Walk Forward Nba Appearance Continuity
- Fail Closed Realized Roster Scoring
- Sequential Validation Choose Blend Weight
- Archive Prediction Run Only When
- Compare Proxy Target Target Training
- Download Nba Pdk Plus Outcomes
- Diagnose Infeasible Lineup Proxy Rounds
- Reject Timestamped Lineups Exports That
- Preset G1 Nuova Squadra Cr
- Return Actionable Non Sensitive State
- Attach Short Flutter Names Canonical
- Build Player Id Catalogue Season
- Regression Tests
- Explicit Bridge Between Nba Games
- Restricted Lineup Proxy Optimizer Feasibility
- Compare Legacy Team Pdk Matchup
- Snapshot Dependency
- Multi Season Production Feature Ablation
- Whether Lineups Api Entity Ids
- Empirical One Week Cr Change
- Reporting Module
- Resolve Frozen Market Names Only
- Resolve Full Or Abbreviated Injury
- Post Hoc Calibration Error Walk
- Restricted Candidate Universe
- Return Baseline That Must Be
- Convert Nba Mm Ss Minute
- Summarize Cross Fitted Interval Coverage
- Leakage Aware Comparison Single Multi
- Advance Scroll Container That Owns
- Combine Individual One Sided Spreads
- Return One Latest Strictly Pre
- Coach Cr Coach Stats Board
- Train Only Two Part Tail
- Map Current Price Realistic Minutes
- Recover Common Tesseract Confusions Without
- Past Only Walk Forward Validation
- Archive Realized Outcomes Immutably Future
- Schedule Ids Stats Api Season
- Regression Tests
- Predict Game Level Pdk Tuned
- Predict Conditional Nba Rookie Mpg
- Regression Tests
- Apply Coach Credit Multipliers Walk
- Infer High Confidence Target Round
- Infer High Confidence Target Round
- Infer Round Dates Unambiguous Links
- Infer Round Dates Unambiguous Links
- Valid Pdk Target
- Verify Cross Season Candidate Rows
- Validate Lineup Independently Milp Constraints
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Verify Public Player Profile Games
- Infer High Confidence Target Round
- Infer High Confidence Target Round
- Infer High Confidence Target Round
- Matchday Turn Mapping Valid Nba
- Date Assisted Exact Signature Linkage
- Matchup Rest Features Derived Reconstructed
- Activate Flutter Semantics Including Its
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Inventory Pre Lock Snapshot Archives
- Accept Fixture Mappings Or Raw
- Project Utilities
- Player Game Pdk Forecast Feature
- Infer High Confidence Target Round
- Infer High Confidence Target Round
- Convert Measured Text Luminance Status
- Regression Tests
- Regression Tests
- Conditional High Score Tail Model
- Compare Direct Coach Score Forecasting
- Reconstruct Coach Base Score Outcomes
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Return One Latest Strictly Pre
- Contracts That Keep Pre Match
- Resolve Supervised Label Without Mixing
- Regression Tests Strict Time Player
- Training Targets Sourced History Separate
- Coach Win Probability Walk
- Resolve Flutter Indisponibili Label Exactly
- Simulate Coach Scores Without Impossible
- Regression Tests
- Game Team Date Linkage
- Reconcile Market Names Against Player
- Read Only Evidence Required Complete
- Round Game Linkage Uses Exact
- Expanding Origin Oos Production Model
- Diagnose Walk Forward Residuals Season
- Extend Leakage Controlled Pdk Training
- Tune Coach Points Model
- Check Whether Lineups Response Contains
- Merge Per Turn Captures Without
- Pre Lock Lineup Market Availability
- Schedule Archive Validation
- Expanding Origin Uncertainty Calibration Uses
- Integrity Temporal Evidence Archived Pre
- Fit Conservative Affine Mapping Actual
- Collect Stats
- Classify Genuinely Visible Dom Label
- Opponent Matchup Trends Player Opponent
- Production Adapter Multi Season Training
- Cross Season Boxscore Signature Matching
- Production Rolling Features Use Proxy
- Compare Direct Coach Score Forecasting
- Compare Direct Coach Score Forecasting
- Evaluate Past Only Affine Residual
- Build Non Destructive Weekly Row
- Utilities Experiments Pdk Targets
- Roster Rules
- Leakage Regressions Final Season Game
- Regression Tests
- Retry Transient Transport Failures Temporary
- Pregame Monte Carlo Coach Score
- Coach Credit Difference Multiplier
- Transfer Penalty Sensitivity Uses Sequential
- Rookie Score Minutes Calibration
- Past Only Residual Calibration Protocol
- Create Matched Immutable Lineup Variants
- Create Matched Immutable Lineup Variants
- Yield Gameweek Holdouts Trained Only
- Preserve Fixture Derived Rotation Labels
- Regression Tests
- Full Lineup Optimizer Strategy Validation
- Temporal Holdout Leakage Aware Pdk
- Corrected Residual Quantile Direction Is
- Config Py Module
- Regression Tests
- Player Id Resolution
- Pdk Random Forest Blended At
- Paired Game Cluster Bootstrap
- Nba Appearance Continuity Proxy Is
- Schedule Status Archive Validity Matching
- Pdk Score Calibration
- Weekly Round Derivative Is Only
- Project Utilities
- Project Utilities
- Run Prospective Gw1 Backtest
- Run Prospective Gw1 Strategy
- Coach Score Monte Carlo
- Lineups Entity Ids Are Distinct
- Post Selection Calibration Adjusts Forecasts
- Expected Minutes Expected Pdk Per
- H2H Lineup Experiment
- Pdk History Features Proxy History
- Post Match Canonical Actuals Evaluation
- Frozen Prospective Gw1 Holdout
- Derivative Is Not Certified Training
- Weekly Round Archive Internal Integrity
- Exact Season Week Round Player
- Weekly Round Records Lack Verified
- Proportional Minutes Allocator Mechanical Replay
- Post Match Evaluation Unavailable Until
- Package Configuration
- Endpoint Discovery

## God Nodes (most connected - your core abstractions)
1. `Settings` - 215 edges
2. `player_key()` - 132 edges
3. `optimize_top_k_lineups()` - 60 edges
4. `run_season_opener()` - 40 edges
5. `predict_players()` - 39 edges
6. `run_walk_forward_backtest()` - 32 edges
7. `player_contribution_multiplier()` - 30 edges
8. `train_models()` - 29 edges
9. `_sample_players()` - 28 edges
10. `scrape_lineups_market()` - 27 edges

## Surprising Connections (you probably didn't know these)
- `test_historical_team_results_create_distinct_coach_point_priors()` --uses--> `Settings`  [INFERRED]
  tests/test_coach_prior_projection.py → src/dunkest/config.py
- `test_live_lineups_market_bypasses_cached_coach_data()` --uses--> `Settings`  [INFERRED]
  tests/test_coach_schedule_fallback.py → src/dunkest/config.py
- `test_opening_coach_catalog_works_before_schedule_is_published()` --uses--> `Settings`  [INFERRED]
  tests/test_coach_schedule_fallback.py → src/dunkest/config.py
- `test_partial_turn_mapping_keeps_unmatched_coaches_in_candidate_market()` --uses--> `Settings`  [INFERRED]
  tests/test_coach_schedule_fallback.py → src/dunkest/config.py
- `test_authoritative_lineups_turn_snapshot_drops_stale_injury_cache()` --uses--> `Settings`  [INFERRED]
  tests/test_injury_eligibility.py → src/dunkest/config.py

## Import Cycles
- None detected.

## Communities (165 total, 26 thin omitted)

### Community 0 - "Paired Game Cluster Bootstrap Monte"
Cohesion: 0.02
Nodes (70): bootstrap(), main(), bootstrap(), main(), main(), main(), main(), main() (+62 more)

### Community 1 - "Walk Forward Nba Appearance Continuity"
Cohesion: 0.04
Nodes (41): auc(), build_panel(), main(), auc(), build_panel(), main(), auc(), build_panel() (+33 more)

### Community 2 - "Fail Closed Realized Roster Scoring"
Cohesion: 0.05
Nodes (43): json_safe(), BacktestReport, compute_backtest_metrics(), RealizedTeamScore, score_realized_team(), _apply_historical_market_snapshot(), _compare_risk_objectives(), _load_historical_market_snapshot() (+35 more)

### Community 3 - "Sequential Validation Choose Blend Weight"
Cohesion: 0.05
Nodes (39): main(), _metrics(), main(), _metrics(), _model_metrics(), _shrunk_recent_mean(), _walk_forward_predictions(), main() (+31 more)

### Community 4 - "Archive Prediction Run Only When"
Cohesion: 0.07
Nodes (39): main(), parse_utc(), sha256(), main(), proportional_minutes(), reconstruct_expected_score(), build_coach_actuals(), build_player_actuals() (+31 more)

### Community 5 - "Compare Proxy Target Target Training"
Cohesion: 0.07
Nodes (40): main(), score_metrics(), _attach_next_game_schedule(), build_feature_matrix(), _empty_window_features(), _history_features(), _matchup_features(), _normalize_player_opponents() (+32 more)

### Community 6 - "Download Nba Pdk Plus Outcomes"
Cohesion: 0.14
Nodes (29): add_official_plusvalenza(), add_previous_credit_change(), get_coach_data(), get_dunkest_data(), get_future_schedule(), get_injuries(), get_player_data(), get_plusvalenza_history() (+21 more)

### Community 7 - "Diagnose Infeasible Lineup Proxy Rounds"
Cohesion: 0.07
Nodes (19): main(), main(), main(), main(), main(), score_row(), main(), make_model() (+11 more)

### Community 8 - "Reject Timestamped Lineups Exports That"
Cohesion: 0.07
Nodes (22): _check_live_market_freshness(), fetch_opening_coach_market(), fetch_opening_market_pool(), _lineups_hard_out_keys(), _load_credits_csv(), test_historical_gameweek_uses_and_records_only_official_rounds(), test_historical_gameweek_without_official_rounds_returns_no_sample(), test_authoritative_lineups_turn_snapshot_drops_stale_injury_cache() (+14 more)

### Community 9 - "Preset G1 Nuova Squadra Cr"
Cohesion: 0.10
Nodes (19): settings_for_season_opener(), attach_official_pdk_labels(), require_complete_collection(), train_multiseason_models(), _attach_verified_player_matchups(), _filter_coaches_to_target_turn(), get_opening_market(), _load_opening_credit_history() (+11 more)

### Community 10 - "Return Actionable Non Sensitive State"
Cohesion: 0.09
Nodes (21): _advance_fixture_carousel(), _all_fixture_labels(), _all_fixtures_from_accessibility_nodes(), _cap_fixture_lineup_annotations(), _decode_png_rgb(), _eligibility_flag(), _eligible_teams_from_fixture_rows(), _fixture_labels_for_turn() (+13 more)

### Community 11 - "Attach Short Flutter Names Canonical"
Cohesion: 0.08
Nodes (26): _apply_lineup_annotations(), _collect_lineup_annotations(), _collect_lineup_annotations_state(), _flatten_market(), _parse_lineup_label(), _eligible_teams_from_fixture_rows_for_test(), test_column_detection_uses_player_clusters_when_both_columns_left_of_viewport_midpoint(), test_fixture_eligibility_fallback_preserves_a_previously_verified_30_team_slate() (+18 more)

### Community 12 - "Build Player Id Catalogue Season"
Cohesion: 0.09
Nodes (14): add_catalog_frame(), collect(), run_one(), discover_players(), exclude_confirmed_contaminated_seed_rows(), fetch_one(), load_checkpoint(), main() (+6 more)

### Community 13 - "Regression Tests"
Cohesion: 0.26
Nodes (29): Settings, optimize_top_k_lineups(), _sample_players(), test_capital_gain_is_separate_and_uses_finite_difference_shadow_price(), test_current_turn_players_are_not_left_on_the_half_value_bench(), test_duplicate_normalized_player_identity_is_rejected(), test_independent_solution_validator_rejects_modified_score(), test_injury_doubt_players_are_removed_even_if_they_project_well() (+21 more)

### Community 14 - "Explicit Bridge Between Nba Games"
Cohesion: 0.12
Nodes (21): build_gameweek1_mapping_from_lineups(), build_gameweek1_mapping_from_nba_schedule(), _eligible_teams(), ensure_gameweek1_fixture_mapping(), fixture_mapping_path(), _parse_fixture_bool(), save_fixture_mapping(), validate_fixture_mapping() (+13 more)

### Community 15 - "Restricted Lineup Proxy Optimizer Feasibility"
Cohesion: 0.10
Nodes (32): Historical player-game linkage, source team mismatch, and unresolved rows, Restricted historical lineup proxy, optimizer feasibility, coach and transfer assumptions, Official PDK labels, validity flags, and proxy-versus-official history provenance, Missing pre-lock candidate universe and explicit participation outcomes, Production core ensemble, score intervals, and final-inference validation boundary, Production core ensemble: expanding-origin OOS and interval calibration audit, Production PDK history-source ablation, Multi-season production PDK history-source ablation (+24 more)

### Community 16 - "Compare Legacy Team Pdk Matchup"
Cohesion: 0.12
Nodes (23): main(), num(), round_map(), date_series(), main(), summarize_source(), training_integrity(), _canonical_keys() (+15 more)

### Community 17 - "Snapshot Dependency"
Cohesion: 0.08
Nodes (29): Example backtest configuration, Historical snapshot dependency, Official PDK training target, Default 2026/27 settings, 2025 coach to team mapping, 2026/27 coach to team mapping, Example roster configuration, Multi-season opening training (+21 more)

### Community 18 - "Multi Season Production Feature Ablation"
Cohesion: 0.11
Nodes (15): normalize_id(), prepare_logs(), score_rows(), synthetic_logs_from_dunkest(), _fga_missed(), _fta_missed(), pdk_from_boxscore_row(), build_direct_pdk_target() (+7 more)

### Community 19 - "Whether Lineups Api Entity Ids"
Cohesion: 0.10
Nodes (13): main(), norm(), main(), sha256(), main(), sha256(), main(), parse_dt() (+5 more)

### Community 20 - "Empirical One Week Cr Change"
Cohesion: 0.13
Nodes (15): add_capital_gain_forecasts(), _capital_gain_estimator(), _corrections_for_cr(), _cr_band_labels(), _CRAdaptiveCapitalGainRegressor, _estimate_band_corrections(), _features(), fit_capital_gain_model() (+7 more)

### Community 21 - "Reporting Module"
Cohesion: 0.18
Nodes (12): load_roster_yaml(), main(), print_matchday_report(), print_top_lineups(), print_season_opener_report(), _cell(), lineup_details_frame(), print_best_coaches() (+4 more)

### Community 22 - "Resolve Frozen Market Names Only"
Cohesion: 0.13
Nodes (15): collect(), one(), fetch_one(), identity_keys(), load_catalog(), load_checkpoint(), main(), normalize_id() (+7 more)

### Community 23 - "Resolve Full Or Abbreviated Injury"
Cohesion: 0.14
Nodes (18): _match_injury_record(), player_key(), player_surname(), _clean_status(), filter_injured(), _initial_token(), play_probability(), _status_letters() (+10 more)

### Community 24 - "Post Hoc Calibration Error Walk"
Cohesion: 0.10
Nodes (12): main(), metrics(), main(), metric_row(), main(), metric(), main(), md_table() (+4 more)

### Community 25 - "Restricted Candidate Universe"
Cohesion: 0.10
Nodes (24): Official game-level actual reconstruction, Past-only walk-forward training, Candidate-universe supersession note V7, Historical lineup infeasibility audit V1, Game-level lineup experiment V1, V1 paired bootstrap, V1 supersession note, Game-level lineup experiment V2 (+16 more)

### Community 26 - "Return Baseline That Must Be"
Cohesion: 0.15
Nodes (16): allocate_positional_minutes(), _apply_projection_weights(), _fit_matrix(), _fit_projection_weights(), _inference_minutes_baseline(), _inference_rows(), _market_implied_rate(), _market_minutes_prior() (+8 more)

### Community 27 - "Convert Nba Mm Ss Minute"
Cohesion: 0.18
Nodes (13): main(), _attach_collection_report(), _collection_report(), fetch_future_schedule(), fetch_player_game_logs(), _fetch_player_log(), fetch_schedule(), fetch_team_game_logs() (+5 more)

### Community 28 - "Summarize Cross Fitted Interval Coverage"
Cohesion: 0.13
Nodes (14): add_uncertainty_columns(), _conditional_cdf_at_zero(), interval_coverage_by_cohort(), _mixture_quantile(), _piecewise_quantile(), test_ensemble_learns_residuals_and_calibrates_from_temporal_holdout(), _forecast_row(), _quantiles() (+6 more)

### Community 29 - "Leakage Aware Comparison Single Multi"
Cohesion: 0.13
Nodes (15): main(), add_cohort(), markdown_table(), metric(), norm_name(), first_existing(), main(), norm() (+7 more)

### Community 30 - "Advance Scroll Container That Owns"
Cohesion: 0.08
Nodes (10): _advance_fixture_scroll(), _click_fixture(), _fixture_click_diagnostic(), main(), _reset_scrollables(), scrape_lineups_market(), _teams_in_fixtures(), test_advance_fixture_scroll_recognizes_matchup_labels_with_regex_boundaries() (+2 more)

### Community 31 - "Combine Individual One Sided Spreads"
Cohesion: 0.15
Nodes (15): _portfolio_spread(), test_transform_applies_official_coach_multiplier_for_positive_and_negative_scores(), test_transform_is_neutral_when_credit_difference_is_below_one(), test_team_score_standard_deviation_is_shrunk_and_bounded(), test_market_cache_ttl_must_be_positive(), test_season_opener_defaults_to_certified_multiseason_training(), test_top_k_requires_distinct_rosters_and_caps_diversity_setting(), test_training_target_mode_is_validated_and_normalized() (+7 more)

### Community 32 - "Return One Latest Strictly Pre"
Cohesion: 0.18
Nodes (11): apply_groupwise_calibration(), build_full_slate_matchups(), build_leakage_safe_training_rows(), build_oos_calibration_residuals(), build_zero_inclusive_training_rows(), candidate_history_features(), history_bin(), latest_prior_candidates() (+3 more)

### Community 33 - "Coach Cr Coach Stats Board"
Cohesion: 0.16
Nodes (9): fetch_coach_cr_table(), fetch_dunkest_gameweek_players(), fetch_stats_table(), fetch_week_rounds(), _injury_status_from_description(), scrape_injuries(), extract_table(), get_json() (+1 more)

### Community 34 - "Train Only Two Part Tail"
Cohesion: 0.15
Nodes (11): main(), prep_model(), score(), main(), prep_model(), score(), cluster_bootstrap_delta(), main() (+3 more)

### Community 35 - "Map Current Price Realistic Minutes"
Cohesion: 0.17
Nodes (16): _apply_current_role_competition(), _base_minutes(), _cap_minutes_to_current_role(), _cr_minutes(), _cr_minutes_cap(), _lineup_minutes_prior(), _normalize_lineup_group(), predict_players() (+8 more)

### Community 36 - "Recover Common Tesseract Confusions Without"
Cohesion: 0.19
Nodes (11): _fixture_labels_from_batches(), _fixture_observation(), _fixture_pair_key(), _fixture_status_key(), _fixture_statuses_from_screenshot(), _fixture_turn_map_from_batches(), _normalize_ocr_team_code(), _record_fixture_statuses() (+3 more)

### Community 37 - "Past Only Walk Forward Validation"
Cohesion: 0.12
Nodes (19): Pre-lock candidate market coverage, Historical game linkage and source-data provenance, Lineup feasibility and transfer constraints, Rest and schedule features, Role-conditioned matchup features, Dunkest project follow-up — 2026-10-13 V21, Dunkest project follow-up — 2026-10-13 V21, Dunkest project follow-up - 2026-10-13 (v23) (+11 more)

### Community 38 - "Archive Realized Outcomes Immutably Future"
Cohesion: 0.20
Nodes (9): _git_branch(), _git_hash(), _input_fingerprints(), _input_paths(), _json_hash(), _package_versions(), save_post_match_snapshot(), save_run_artifacts() (+1 more)

### Community 39 - "Schedule Ids Stats Api Season"
Cohesion: 0.11
Nodes (18): Dunkest schedule ID ↔ NBA season inventory (v2), Dunkest schedule ID ↔ NBA season inventory (v3), Dunkest schedule ID ↔ NBA season inventory (v4), Dunkest schedule ID ↔ NBA season inventory (v5), Dunkest schedule ID ↔ NBA season inventory (v6), Dunkest schedule ID ↔ NBA season inventory (v7), Schedule IDs and stats API season IDs are distinct namespaces, Status-aware schedule and archive validation (+10 more)

### Community 40 - "Regression Tests"
Cohesion: 0.19
Nodes (17): predict_coach_points(), test_all_zero_team_forecasts_do_not_collapse_historical_coach_strength(), test_cheap_coach_gets_matchup_projection_against_weak_defense(), test_coach_matchup_adjusts_for_projected_roster_strength(), test_coach_opener_uses_prior_team_coach_score_when_matchup_is_missing(), test_coach_price_does_not_stand_in_for_team_strength_without_matchup_data(), test_coach_synthetic_matchup_uses_fallback_date_when_primary_date_is_nullable(), test_constant_game_scores_use_neutral_correlation_without_runtime_warning() (+9 more)

### Community 41 - "Predict Game Level Pdk Tuned"
Cohesion: 0.24
Nodes (10): _date(), _load_bundle(), _load_nba_history(), _nba_features(), _normal_id(), _pdk_features(), predict_historical_pdk(), test_historical_feature_helpers_return_missing_values_for_empty_history() (+2 more)

### Community 42 - "Predict Conditional Nba Rookie Mpg"
Cohesion: 0.23
Nodes (8): _college_features(), _historical_rookie_minutes_prior(), load_college_rookie_priors(), _number(), _rookie_sample_weights(), _historical_and_current_classes(), test_rookie_minutes_prior_uses_past_classes_and_passes_temporal_baseline(), test_rookie_prior_prefers_verified_official_dunkest_labels()

### Community 43 - "Regression Tests"
Cohesion: 0.15
Nodes (12): _game_log(), _install_fake_player_api(), get_data_frames(), test_incomplete_player_collection_is_not_cached(), test_player_collection_normalizes_requested_names_and_reports_unmatched(), test_player_collection_reports_failed_entities_after_bounded_retries(), test_player_limit_marks_truncated_collection_incomplete(), test_prior_season_fallback_reports_partial_player_logs() (+4 more)

### Community 44 - "Apply Coach Credit Multipliers Walk"
Cohesion: 0.20
Nodes (7): main(), transform(), main(), transform(), main(), transform(), coach_coefficient()

### Community 45 - "Infer High Confidence Target Round"
Cohesion: 0.19
Nodes (7): attach_matchup_features(), attach_player_opponent_history(), attach_rest_schedule_features(), build_features(), main(), make_model(), metric_row()

### Community 46 - "Infer High Confidence Target Round"
Cohesion: 0.19
Nodes (7): attach_matchup_features(), attach_player_opponent_history(), attach_rest_schedule_features(), build_features(), main(), make_model(), metric_row()

### Community 47 - "Infer Round Dates Unambiguous Links"
Cohesion: 0.19
Nodes (7): attach_matchup_features(), attach_player_opponent_history(), attach_rest_schedule_features(), build_features(), main(), make_model(), metric_row()

### Community 48 - "Infer Round Dates Unambiguous Links"
Cohesion: 0.19
Nodes (7): attach_matchup_features(), attach_player_opponent_history(), attach_rest_schedule_features(), build_features(), main(), make_model(), metric_row()

### Community 49 - "Valid Pdk Target"
Cohesion: 0.18
Nodes (15): Convex ensemble weights, Untouched 2025/26 final holdout, Frozen 2026/27 GW1 holdout, Shrunk player-versus-opponent history features, Official-valid PDK target, Expanding-window walk-forward validation, Dunkest end-to-end model audit, Walk-forward ensemble-weight tuning (+7 more)

### Community 50 - "Verify Cross Season Candidate Rows"
Cohesion: 0.19
Nodes (7): main(), normalize_game_id(), round_half_up_1dp(), half_up_1dp(), main(), main(), round_half_up_1dp()

### Community 51 - "Validate Lineup Independently Milp Constraints"
Cohesion: 0.27
Nodes (7): LineupSolution, _pick_module(), _solve_once(), _validate_optimizer_inputs(), validate_solution(), transfer_count(), run_optimize()

### Community 52 - "Return One Latest Strictly Pre"
Cohesion: 0.25
Nodes (7): build_full_slate_matchups(), build_leakage_safe_training_rows(), candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 53 - "Return One Latest Strictly Pre"
Cohesion: 0.25
Nodes (7): build_full_slate_matchups(), build_leakage_safe_training_rows(), candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 54 - "Return One Latest Strictly Pre"
Cohesion: 0.25
Nodes (7): build_full_slate_matchups(), build_leakage_safe_training_rows(), candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 55 - "Verify Public Player Profile Games"
Cohesion: 0.23
Nodes (6): eq(), main(), main(), row_name(), count(), main()

### Community 56 - "Infer High Confidence Target Round"
Cohesion: 0.24
Nodes (6): attach_matchup_features(), attach_player_opponent_history(), build_features(), main(), make_model(), metric_row()

### Community 57 - "Infer High Confidence Target Round"
Cohesion: 0.24
Nodes (6): attach_matchup_features(), attach_player_opponent_history(), build_features(), main(), make_model(), metric_row()

### Community 58 - "Infer High Confidence Target Round"
Cohesion: 0.24
Nodes (6): attach_matchup_features(), attach_player_opponent_history(), build_features(), main(), make_model(), metric_row()

### Community 59 - "Matchday Turn Mapping Valid Nba"
Cohesion: 0.17
Nodes (12): Neutral-credit coach base-score reconstruction, Dunkest matchday/turn mapping to valid NBA games, Dunkest game-validity cross-endpoint discrepancy, Lineup-level historical replay and missing historical snapshots, Past-only residual correction, Quantitative Dunkest audit — 2026-10-07, Past-only residual correction experiment — V1, Dunkest autonomous code validation — 2026-10-14 (+4 more)

### Community 60 - "Date Assisted Exact Signature Linkage"
Cohesion: 0.26
Nodes (12): Date-assisted exact-signature linkage, Complete timestamped pre-lock market snapshot, Source team versus official game-date NBA team, Date-assisted exact-signature linkage paired walk-forward evaluation, Historical Dunkest game-linked row dataset V1, Historical game-linked rows V3 date-assisted exact-signature linkage, Historical lineup candidate-universe audit supersession note V1, Historical lineup candidate-universe audit supersession note V2 (+4 more)

### Community 61 - "Matchup Rest Features Derived Reconstructed"
Cohesion: 0.24
Nodes (11): Historical matchup and rest features derived from reconstructed dates and strictly prior team-game history, Lagged-market lineup proxy uses latest prior observed price and form; incomplete pre-lock candidates and missing historical coach prices limit market-optimum claims, Historical lineup lagged market V5: 409-round proxy comparison; not a complete historical market backtest, Paired lineup proxy: matchup V2 versus past-only rest/schedule V6, Paired bootstrap for rest/schedule V6 versus matchup V2 lineup proxy, Strict lineup proxy coverage: only 3 paired rounds had all ten outcomes observed, Lagged-credit matchup-aware player-score walk-forward V1, Expanded matchup features walk-forward V2 (+3 more)

### Community 62 - "Activate Flutter Semantics Including Its"
Cohesion: 0.20
Nodes (5): main(), on_response(), main(), write_jsonl(), _enable_flutter_accessibility()

### Community 63 - "Return One Latest Strictly Pre"
Cohesion: 0.29
Nodes (6): build_leakage_safe_training_rows(), candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 64 - "Return One Latest Strictly Pre"
Cohesion: 0.27
Nodes (6): build_candidate_h2h(), candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 65 - "Inventory Pre Lock Snapshot Archives"
Cohesion: 0.22
Nodes (4): main(), metadata_for(), _annotations_from_ocr_tsv(), test_ocr_fallback_reads_only_names_between_unavailable_heading_and_legend()

### Community 66 - "Accept Fixture Mappings Or Raw"
Cohesion: 0.35
Nodes (5): _next_game_context(), _normalize_schedule_frame(), _recent_shrunk_mean(), _roster_point_adjustments(), _team_profiles()

### Community 67 - "Project Utilities"
Cohesion: 0.18
Nodes (10): name, manjunathshiva/Qwen3.6-35B-A3B-tq3a-tqTe-down4-g64, baseURL, provider, turboquant, $schema, models, name (+2 more)

### Community 68 - "Player Game Pdk Forecast Feature"
Cohesion: 0.18
Nodes (11): Dunkest backtest — consolidated audit, Dunkest PDK feature-family comparison — 2026-10-13, Player-game PDK forecast feature-family evaluation, Persisted v3 dataset and V8/V9 prediction parity — v1, Dunkest — Phase B model and strategy comparison, Pre-match snapshot authenticity audit — V1, Pre-match snapshot authenticity audit — V1, Follow-up affidabilità previsioni Dunkest — 20261012T152844Z_dcb3a29b (+3 more)

### Community 69 - "Infer High Confidence Target Round"
Cohesion: 0.27
Nodes (5): attach_matchup_features(), build_features(), main(), make_model(), metric_row()

### Community 70 - "Infer High Confidence Target Round"
Cohesion: 0.27
Nodes (5): attach_matchup_features(), build_features(), main(), make_model(), metric_row()

### Community 71 - "Convert Measured Text Luminance Status"
Cohesion: 0.18
Nodes (8): _fixture_card_pixel_status(), _fixture_status_from_luminance(), _visible_word_luminance(), test_fixture_card_pixel_fallback_leaves_selected_dark_tile_unknown(), test_fixture_card_pixel_fallback_reads_each_team_on_its_own_row(), test_fixture_status_from_luminance_has_gray_uncertainty_band(), test_ocr_ink_luminance_resists_antialiasing_gray_pixel_majority(), test_selected_dark_fixture_tile_is_not_misread_as_black_team_text()

### Community 72 - "Regression Tests"
Cohesion: 0.33
Nodes (7): _console_output(), _predictions(), _solution(), test_coach_report_does_not_rank_historical_prior_as_a_matchup_pick(), test_integer_column_formats_pandas_float_values_without_crashing(), test_matchday_report_uses_readable_rich_sections(), test_season_opener_report_uses_readable_rich_sections()

### Community 73 - "Regression Tests"
Cohesion: 0.27
Nodes (8): _fixtures(), test_coach_overtime_is_inferred_from_summed_player_minutes(), test_coach_score_is_not_fabricated_when_overtime_cannot_be_inferred(), test_coach_scores_are_linked_to_final_nba_fixture_ids(), test_date_only_schedule_uses_conservative_postgame_cutoff(), test_exact_kickoff_schedule_uses_four_hour_cutoff(), test_invalid_dunkest_result_rows_are_not_counted_as_actuals(), test_player_actuals_join_by_player_opponent_date_and_verified_fixture()

### Community 74 - "Conditional High Score Tail Model"
Cohesion: 0.24
Nodes (10): Conditional high-score tail model, Conditional tail mixture blend, Paired date-cluster bootstrap, Conditional tail blend — V1, Conditional high-score tail model — V1, Conditional high-score tail model — V2, Conditional tail model paired bootstrap — V1, Sequential blend-weight validation — V1 (+2 more)

### Community 75 - "Compare Direct Coach Score Forecasting"
Cohesion: 0.27
Nodes (6): main(), _metric(), stable_seed(), _team_sd(), coach_points_from_outcomes(), test_vectorized_coach_score_matches_rule_thresholds_and_overtime()

### Community 76 - "Reconstruct Coach Base Score Outcomes"
Cohesion: 0.31
Nodes (5): add_pregame_features(), main(), make_model(), make_outcomes(), score_metrics()

### Community 77 - "Return One Latest Strictly Pre"
Cohesion: 0.31
Nodes (5): candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 78 - "Return One Latest Strictly Pre"
Cohesion: 0.31
Nodes (5): candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 79 - "Return One Latest Strictly Pre"
Cohesion: 0.31
Nodes (5): candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 80 - "Return One Latest Strictly Pre"
Cohesion: 0.31
Nodes (5): candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 81 - "Return One Latest Strictly Pre"
Cohesion: 0.31
Nodes (5): candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 82 - "Return One Latest Strictly Pre"
Cohesion: 0.31
Nodes (5): candidate_history_features(), latest_prior_candidates(), main(), make_model(), score_lineup()

### Community 83 - "Contracts That Keep Pre Match"
Cohesion: 0.22
Nodes (5): DataTiming, validate_player_fixture_associations(), validate_prematch_features(), test_prematch_feature_guard_rejects_postmatch_target_and_late_data(), test_official_pdk_overlay_fields_are_forbidden_as_features()

### Community 84 - "Resolve Supervised Label Without Mixing"
Cohesion: 0.29
Nodes (7): _resolve_training_target(), _logs_with_proxy_scores(), test_auto_training_target_falls_back_when_official_coverage_is_small(), test_auto_training_target_uses_official_labels_only_above_threshold(), test_explicit_training_target_overrides_auto_selection(), test_official_pdk_overlay_joins_by_identity_and_preserves_proxy(), test_official_pdk_overlay_without_matches_is_not_applied()

### Community 85 - "Regression Tests Strict Time Player"
Cohesion: 0.31
Nodes (5): _source_rows(), test_h2h_features_are_missing_when_no_prior_opponent_game(), test_h2h_features_exclude_target_day_and_invalid_pdk(), test_h2h_lookup_does_not_mix_other_opponents(), test_latest_prior_candidates_carries_forward_last_known_credit_without_future_rows()

### Community 86 - "Training Targets Sourced History Separate"
Cohesion: 0.22
Nodes (9): Downstream impact of confirmed weekly-round contamination — V1, Downstream impact of confirmed weekly-round contamination — V2, Training targets sourced from official history, separate from weekly-round archive, Dunkest weekly-round quarantine/review manifest (v1), Dunkest weekly-round quarantine/review manifest (v2), Isolated exact-signature matches remain manual-review candidates, Verified cross-season rows in Dunkest weekly-round archive (v1), Confirmed season-5/week-43/round-2 PHI–MIN contamination cluster (+1 more)

### Community 87 - "Coach Win Probability Walk"
Cohesion: 0.42
Nodes (6): _calibration_bins(), main(), period_report(), _metrics(), _shrunk_recent_mean(), _walk_forward_predictions()

### Community 88 - "Resolve Flutter Indisponibili Label Exactly"
Cohesion: 0.25
Nodes (8): _match_unavailable_to_market(), by_cr(), by_initial_surname(), by_key(), by_surname(), by_token(), pick(), test_teamless_injury_annotation_resolves_only_a_unique_surname()

### Community 89 - "Simulate Coach Scores Without Impossible"
Cohesion: 0.22
Nodes (5): _coach_score_distribution(), _expected_coach_pdk(), coach_score_summary(), _simulate_matchup_scores(), test_coach_simulation_never_returns_tied_final_scores()

### Community 90 - "Regression Tests"
Cohesion: 0.22
Nodes (5): test_corrupt_parquet_is_a_cache_miss(), test_fit_matrix_replaces_infinite_values_with_training_median(), test_settings_reject_unknown_optimizer_objective(), test_training_rejects_missing_usable_features(), test_write_parquet_publishes_data_and_metadata()

### Community 91 - "Game Team Date Linkage"
Cohesion: 0.29
Nodes (8): Historical game, team, and date linkage, Past-only team and opponent rest and schedule features, Historical lagged-credit walk-forward V6: past-only rest and schedule features, Historical lagged-credit walk-forward V7: corrected historical game-team linkage, Historical lagged-credit walk-forward V8: date-assisted exact-signature linkage, Historical lagged-credit walk-forward V9: persisted date-assisted linkage, Audit of legacy-only opponent coverage V1, Historical lineup rest and schedule robustness audit

### Community 92 - "Reconcile Market Names Against Player"
Cohesion: 0.36
Nodes (4): load_collector(), main(), norm(), sha256()

### Community 93 - "Read Only Evidence Required Complete"
Cohesion: 0.39
Nodes (4): columns(), inventory(), main(), metadata()

### Community 94 - "Round Game Linkage Uses Exact"
Cohesion: 0.36
Nodes (8): Coverage audit of historical matchup team-link correction, Paired walk-forward evaluation of matchup team-link correction V7, Historical Dunkest round-to-game mapping audit using full-stat signatures, Diagnosis of 19 residual unmatched historical rows, Classification of unmatched historical weekly rows V2, Team identity diagnosis of unmatched historical weekly rows V3, Coarse survey of historical Dunkest schedule IDs, Round-to-game linkage uses exact player, season, PDK and box-score signatures; source team identity may differ from historical NBA game team

### Community 95 - "Expanding Origin Oos Production Model"
Cohesion: 0.36
Nodes (5): interval_stats(), main(), md_table(), metric_row(), _ensemble_predict()

### Community 96 - "Diagnose Walk Forward Residuals Season"
Cohesion: 0.32
Nodes (3): main(), metrics(), paired_delta_ci()

### Community 97 - "Extend Leakage Controlled Pdk Training"
Cohesion: 0.54
Nodes (5): attach_nba_history(), load_nba_history(), main(), normalize_id(), rebuild_pdk_history()

### Community 98 - "Tune Coach Points Model"
Cohesion: 0.46
Nodes (5): main(), _metrics(), _period_metrics(), _shrunk_recent_mean(), _walk_forward_predictions()

### Community 99 - "Check Whether Lineups Response Contains"
Cohesion: 0.25
Nodes (5): _fixture_present_in_market_response(), _latest_fixture_market_matches(), _wait_for_fixture_market(), test_already_selected_fixture_is_verified_from_its_api_market(), test_latest_fixture_market_match_does_not_accept_an_old_response()

### Community 100 - "Merge Per Turn Captures Without"
Cohesion: 0.25
Nodes (5): _lineups_browser_profile_dir(), merge_turn_market_snapshots(), test_lineups_browser_profile_can_be_configured(), test_lineups_browser_profile_is_persistent_and_outside_project_by_default(), test_merge_turn_market_snapshots_preserves_all_turns_and_hard_outs()

### Community 101 - "Pre Lock Lineup Market Availability"
Cohesion: 0.43
Nodes (6): NBA appearance-continuity proxy and missing-row label caveat, Pre-lock lineup market and availability snapshots, Complete-lineup backtest readiness audit V1, Complete-lineup backtest readiness audit V2, NBA appearance-continuity proxy walk-forward audit V1, NBA appearance-continuity proxy walk-forward audit V2

### Community 102 - "Schedule Archive Validation"
Cohesion: 0.43
Nodes (7): Fantasy round to NBA game calendar mapping, Dunkest week/round calendar linkage audit v1, Official schedule and archive validation, Dunkest official schedule vs archive — 2024/25, Dunkest official schedule vs archive — 2024/25 (v2, status-aware), Dunkest official schedule vs archive — 2024/25 (v3, status-aware), Dunkest schedule ID ↔ NBA season inventory (v1)

### Community 103 - "Expanding Origin Uncertainty Calibration Uses"
Cohesion: 0.29
Nodes (7): Single-season vs multi-season Dunkest PDK training — V1, Implementazione dei tre workstream Dunkest — 2026-10-14, Expanding-origin uncertainty calibration uses prior-season residuals, Lineup scoring requires authentic pre-lock snapshots and fixture-linked actuals, Multi-season trainer uses certified prior-season targets, Transfer-malus sensitivity — sequential lineup proxy, Paired strategy comparison: V6 vs V7

### Community 104 - "Integrity Temporal Evidence Archived Pre"
Cohesion: 0.43
Nodes (3): main(), parse_dt(), sha256()

### Community 106 - "Collect Stats"
Cohesion: 0.52
Nodes (5): extract_rounds(), main(), output_path(), save_manifest(), task_key()

### Community 107 - "Classify Genuinely Visible Dom Label"
Cohesion: 0.29
Nodes (5): _fixture_team_eligibility(), _resolve_fixture_team_status(), test_fixture_status_resolution_prefers_confident_dom_color(), test_fixture_status_resolution_uses_screenshot_only_when_dom_color_is_unknown(), test_fixture_team_eligibility_uses_visible_css_color_and_opacity()

### Community 108 - "Opponent Matchup Trends Player Opponent"
Cohesion: 0.47
Nodes (5): Lagged player form and credit features, Opponent matchup trends and player-versus-opponent history, Historical lagged-credit walk-forward V5: role-conditioned matchup interactions, Historical lagged-credit walk-forward V1, Expanded matchup features paired cluster bootstrap

### Community 109 - "Production Adapter Multi Season Training"
Cohesion: 0.53
Nodes (6): Production-adapter multi-season training validation, Model comparison: training window, recent-score baselines and cohorts V1, Model comparison: training window, recent-score baselines and cohorts V2, Multi-season production-adapter walk-forward validation V1, Multi-season production-adapter walk-forward validation V2, Multi-season production-adapter walk-forward validation V3

### Community 110 - "Cross Season Boxscore Signature Matching"
Cohesion: 0.33
Nodes (6): Weekly-round exact boxscore signature corroboration (v1), Dunkest weekly-round cross-season integrity audit (v1), Cross-season boxscore signature matching, Dunkest weekly-round cross-season integrity audit (v2), Weekly-round cross-season candidate corroboration (v1), Official player-history PDK corroboration

### Community 111 - "Production Rolling Features Use Proxy"
Cohesion: 0.33
Nodes (6): Official PDK target-mode review (v1), Official PDK target-mode review (v2), Production rolling features use proxy PDK while official labels may be selected, Proxy-target vs official-target training — 2025/26 (v1), Common-row proxy versus official target OOF comparison, Proxy-target vs official-target training — 2025/26 (v2, common-row comparison)

### Community 112 - "Compare Direct Coach Score Forecasting"
Cohesion: 0.53
Nodes (4): main(), _metric(), stable_seed(), _team_sd()

### Community 113 - "Compare Direct Coach Score Forecasting"
Cohesion: 0.53
Nodes (4): main(), _metric(), stable_seed(), _team_sd()

### Community 114 - "Evaluate Past Only Affine Residual"
Cohesion: 0.47
Nodes (3): ci_delta(), main(), metrics()

### Community 115 - "Build Non Destructive Weekly Row"
Cohesion: 0.47
Nodes (3): main(), n(), sha()

### Community 117 - "Roster Rules"
Cohesion: 0.80
Nodes (3): expected_player_points(), player_contribution_multiplier(), RosterRules

### Community 118 - "Leakage Regressions Final Season Game"
Cohesion: 0.53
Nodes (4): _rows(), test_final_holdout_h2h_does_not_mix_opponents(), test_final_holdout_h2h_excludes_same_day_and_shrinks_prior_history(), test_final_holdout_h2h_falls_back_to_prior_form_without_history()

### Community 119 - "Regression Tests"
Cohesion: 0.33
Nodes (4): test_cross_fitted_calibration_uses_only_valid_oof_residuals(), test_train_models_accepts_positive_sample_weights_and_records_provenance(), test_train_models_explicit_official_target_changes_supervised_label_not_features(), test_train_models_rejects_nonpositive_sample_weights()

### Community 121 - "Pregame Monte Carlo Coach Score"
Cohesion: 0.70
Nodes (5): Pregame Monte Carlo coach-score distribution, Coach Monte Carlo backtest — supersession note, Coach score forecast: direct model vs pregame Monte Carlo — V1, Coach score forecast: direct model vs pregame Monte Carlo — V2, Coach score forecast: direct model vs pregame Monte Carlo — V3

### Community 122 - "Coach Credit Difference Multiplier"
Cohesion: 0.60
Nodes (5): Official coach credit-difference multiplier, Coach official multiplier sensitivity — V1, Coach official multiplier sensitivity — V2, Coach official multiplier sensitivity — V3, Coach multiplier sensitivity audit — supersession note

### Community 123 - "Transfer Penalty Sensitivity Uses Sequential"
Cohesion: 0.60
Nodes (4): Sequential lineup transfer-penalty scenarios V1, Sequential lineup transfer-penalty scenarios V2: common 5-point scoring malus, Paired bootstrap audit of sequential transfer-penalty scenarios, Transfer penalty sensitivity uses sequential simulated rosters and a fixed scoring malus; incomplete candidates constrain conclusions

### Community 124 - "Rookie Score Minutes Calibration"
Cohesion: 0.40
Nodes (5): Dunkest rookie projection balance audit — 2026-10-12, Rookie-specific official PDK walk-forward validation, Plusvalenza prediction and uncertainty calibration, Rookie score and minutes calibration, Rookie and plusvalenza calibration audit — 2026-10-13

### Community 125 - "Past Only Residual Calibration Protocol"
Cohesion: 0.40
Nodes (5): Tail-specialist hybrid vs V9 — V1, V9 past-only residual calibration audit, V9 past-only residual calibration protocol, V9 walk-forward residual-segment audit, Expanding-origin OOF residual diagnostics

### Community 126 - "Create Matched Immutable Lineup Variants"
Cohesion: 0.60
Nodes (3): lineup_frame(), main(), sha256()

### Community 127 - "Create Matched Immutable Lineup Variants"
Cohesion: 0.60
Nodes (3): lineup_frame(), main(), sha256()

### Community 128 - "Yield Gameweek Holdouts Trained Only"
Cohesion: 0.50
Nodes (3): _expanding_week_splits(), test_plusvalenza_validation_uses_only_strictly_earlier_weeks(), test_temporal_validation_skips_weeks_without_enough_past_rows()

### Community 129 - "Preserve Fixture Derived Rotation Labels"
Cohesion: 0.50
Nodes (3): _sanitize_lineup_annotations(), test_team_wide_starter_count_is_preserved_without_fixture_scope(), test_valid_starting_five_is_preserved()

### Community 130 - "Regression Tests"
Cohesion: 0.60
Nodes (3): _games(), test_neutral_site_game_is_forecast_without_home_advantage(), test_same_day_results_do_not_leak_into_other_same_day_forecasts()

### Community 131 - "Full Lineup Optimizer Strategy Validation"
Cohesion: 0.67
Nodes (4): Dunkest optimizer, ensemble, calibration and matchup audit — 2026-10-14, Dunkest — production ensemble OOS validation and lineup-strategy readiness, Full-lineup and optimizer strategy validation readiness, Expanding-origin production ensemble and residual interval calibration

### Community 132 - "Temporal Holdout Leakage Aware Pdk"
Cohesion: 0.50
Nodes (4): Dunkest PDK: fixed holdout training 2020/21–2024/25, test 2025/26, Temporal holdout and leakage-aware PDK evaluation, Dunkest PDK model tuning — 20261012_v1, Dunkest PDK predictor search — train-only V1

### Community 133 - "Corrected Residual Quantile Direction Is"
Cohesion: 0.50
Nodes (4): Dunkest uncertainty calibration — expanding-origin OOS audit, Superseded uncertainty audit — 2026-10-14, Dunkest uncertainty calibration — expanding-origin OOS audit, Corrected residual quantile direction is authoritative

### Community 135 - "Regression Tests"
Cohesion: 0.50
Nodes (3): test_live_lineups_market_bypasses_cached_coach_data(), test_opening_coach_catalog_works_before_schedule_is_published(), test_partial_turn_mapping_keeps_unmatched_coaches_in_candidate_market()

### Community 136 - "Player Id Resolution"
Cohesion: 0.67
Nodes (3): Player ID resolution, Dunkest 2026–27 Player ID Resolution Audit V1, Dunkest 2026–27 Player ID Resolution Audit V2

### Community 137 - "Pdk Random Forest Blended At"
Cohesion: 1.00
Nodes (3): Historical PDK Random Forest blended at 20 percent for eligible players; holdout gain over simple baseline does not establish superiority over prior production ensemble, Historical PDK model production blend audit: 20 percent historical model blend, Historical PDK model production blend integration and holdout audit

### Community 138 - "Paired Game Cluster Bootstrap"
Cohesion: 0.67
Nodes (3): Paired game-cluster bootstrap, Coach Monte Carlo paired bootstrap — supersession note, Paired bootstrap: coach-score Monte Carlo vs baselines — V1

### Community 139 - "Nba Appearance Continuity Proxy Is"
Cohesion: 0.67
Nodes (3): NBA appearance-continuity proxy is not production Dunkest p_play, NBA appearance-continuity proxy — walk-forward audit, Participation / DNP label-readiness audit

### Community 140 - "Schedule Status Archive Validity Matching"
Cohesion: 0.67
Nodes (3): Validazione del calendario ufficiale Dunkest rispetto all’archivio locale, Official Dunkest schedule vs local archive — v2 (status-aware), Official schedule status and archive validity matching

### Community 141 - "Pdk Score Calibration"
Cohesion: 0.67
Nodes (3): Dunkest PDK calibration and error audit, Dunkest PDK score calibration experiment, PDK score calibration

### Community 142 - "Weekly Round Derivative Is Only"
Cohesion: 0.67
Nodes (3): Dunkest stats endpoint scope audit (v1), Weekly-round audit derivative (v1), Weekly-round derivative is audit-only and not certified for training

## Knowledge Gaps
- **148 isolated node(s):** `dunkest-optimizer`, `PYTHONPATH`, `PYTHONPATH`, `PYTHONPATH`, `PYTHONPATH` (+143 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 707 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `player_key()` connect `Resolve Full Or Abbreviated Injury` to `Paired Game Cluster Bootstrap Monte`, `Walk Forward Nba Appearance Continuity`, `Fail Closed Realized Roster Scoring`, `Sequential Validation Choose Blend Weight`, `Archive Prediction Run Only When`, `Compare Proxy Target Target Training`, `Download Nba Pdk Plus Outcomes`, `Reject Timestamped Lineups Exports That`, `Preset G1 Nuova Squadra Cr`, `Return Actionable Non Sensitive State`, `Attach Short Flutter Names Canonical`, `Regression Tests`, `Compare Legacy Team Pdk Matchup`, `Resolve Frozen Market Names Only`, `Return Baseline That Must Be`, `Convert Nba Mm Ss Minute`, `Leakage Aware Comparison Single Multi`, `Return One Latest Strictly Pre`, `Map Current Price Realistic Minutes`, `Predict Game Level Pdk Tuned`, `Predict Conditional Nba Rookie Mpg`, `Validate Lineup Independently Milp Constraints`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Resolve Flutter Indisponibili Label Exactly`, `Merge Per Turn Captures Without`, `Build Non Destructive Weekly Row`, `Roster Rules`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 186 inferred relationships involving `Settings` (e.g. with `main()` and `score_rows()`) actually correct?**
  _`Settings` has 186 INFERRED edges - model-reasoned connections that need verification._
- **What connects `dunkest-optimizer`, `PYTHONPATH`, `PYTHONPATH` to the rest of the system?**
  _148 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Paired Game Cluster Bootstrap Monte` be split into smaller, more focused modules?**
  _Cohesion score 0.02360248447204969 - nodes in this community are weakly interconnected._
- **Why does `Settings` connect `Regression Tests` to `Walk Forward Nba Appearance Continuity`, `Fail Closed Realized Roster Scoring`, `Compare Proxy Target Target Training`, `Config Py Module`, `Download Nba Pdk Plus Outcomes`, `Reject Timestamped Lineups Exports That`, `Preset G1 Nuova Squadra Cr`, `Regression Tests`, `Explicit Bridge Between Nba Games`, `Compare Legacy Team Pdk Matchup`, `Multi Season Production Feature Ablation`, `Whether Lineups Api Entity Ids`, `Reporting Module`, `Resolve Full Or Abbreviated Injury`, `Post Hoc Calibration Error Walk`, `Return Baseline That Must Be`, `Convert Nba Mm Ss Minute`, `Summarize Cross Fitted Interval Coverage`, `Leakage Aware Comparison Single Multi`, `Combine Individual One Sided Spreads`, `Return One Latest Strictly Pre`, `Coach Cr Coach Stats Board`, `Map Current Price Realistic Minutes`, `Archive Realized Outcomes Immutably Future`, `Regression Tests`, `Regression Tests`, `Validate Lineup Independently Milp Constraints`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Regression Tests`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Return One Latest Strictly Pre`, `Resolve Supervised Label Without Mixing`, `Regression Tests`, `Expanding Origin Oos Production Model`, `Collect Stats`, `Regression Tests`, `Create Matched Immutable Lineup Variants`, `Create Matched Immutable Lineup Variants`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Should `Walk Forward Nba Appearance Continuity` be split into smaller, more focused modules?**
  _Cohesion score 0.042455536431440045 - nodes in this community are weakly interconnected._
- **Why does `_match_unavailable_to_market()` connect `Resolve Flutter Indisponibili Label Exactly` to `Return Actionable Non Sensitive State`, `Attach Short Flutter Names Canonical`, `Advance Scroll Container That Owns`, `Resolve Full Or Abbreviated Injury`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._