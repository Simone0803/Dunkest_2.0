# Dunkest model and coach pipeline audit — 2026-10-15 V1

## User objective and scope

The production goal is to forecast this season's player PDK and future credit changes from available historical Dunkest outcomes, NBA box scores, current credits/roles, verified matchups, and current injury/availability information. Coach choice must be based on the opponent, projected team scores, official coach scoring rules and CR opportunity cost. Historical full-lineup backtesting is not a prerequisite and was not pursued in this pass.

No unavailable historical snapshots were reconstructed. No model weights were tuned. The 2026/27 GW1 prospective test remains frozen until 2026-10-23 12:00 UTC.

## Verified player-model path

- The current opening configuration sets `training_target: target_pdk_official`, `opening_multiseason_training: true`, `opening_use_pdk_cr_proxy: false`, and `historical_pdk_blend_weight: 0.20`.
- `train_multiseason_models()` trains the primary model on the certified Dunkest PDK dataset `data/processed/dunkest_pdk_game_training_2020-25_v1.parquet` (official labeled seasons 2020/21–2024/25). The separate historical Extra Trees predictor is blended conservatively and is not a substitute for the primary trainer.
- The inference feature builder uses the complete 2025/26 NBA player/team game logs where available; the latest GW1 run manifest records 24,100 player rows and 2,460 team rows, both marked complete. Those are NBA logs/features, not invented Dunkest labels.
- Matchup features include opponent defensive/pace statistics and lagged player-vs-opponent PDK rates; the upcoming opponent is attached from the verified Dunkest fixture mapping. Current injuries/availability are joined to players and hard OUT players are excluded.
- The plusvalenza model is trained only from the available official plus/minus samples, predicts ΔCR in CR units, uses past-only walk-forward residual calibration, and leaves forecasts unavailable when support is insufficient. Its current prior-season file contains sparse official sample gameweeks, so it must not be interpreted as a complete historical market archive.
- Existing audit reports show historical player-level MAE improvements for certain challenger models, but those challengers have not been promoted where feature schema/production-path evidence is insufficient. No production player-model weights were changed.

## Coach-selection issues fixed

### 1. Removed invented 112–112 score fallback

Previously, when team logs were missing but a fixture was verified, `_next_game_context()` assigned both teams 112 points, marked the matchup forecast available, and allowed the optimizer to rank coaches. This could make a coach look attractive because of CR multipliers even though there was no team-score forecast.

Now a verified matchup with no usable team history preserves the opponent/fixture identity but sets `coach_projection_source=missing_team_history`, leaves score estimates unknown, and sets `matchup_projection_available=false`. The optimizer excludes it and fails closed if no coach has a real matchup-based score forecast.

### 2. Removed imputation of missing opponent coach CR

Previously, a missing `opponent_coach_cr` was filled with the selected coach's own CR. Since the official coach coefficient depends on the actual difference between the two coach prices, this silently fabricated a neutral price gap.

Now missing opponent CR stays missing, the coach score forecast is marked unavailable with `coach_projection_source=missing_opponent_coach_cr`, and the candidate cannot enter optimization. No estimated or copied opponent price is used.

### 3. Coach cost and matchup are visible and auditable

- The MILP already selects players and coach jointly under the 95 CR budget, the max-three-per-NBA-team constraint including the coach, the expected coach PDK, and the transfer penalty. A regression test verifies that it trades down from a more expensive coach when doing so funds a better joint player roster.
- Coach recommendations now expose opponent, win probability, expected point margin, own CR, opponent coach CR, CR gap, expected coach PDK and PDK/CR. The PDK/CR ratio is a diagnostic, not the optimization objective; the solver's joint budget-constrained objective remains authoritative.
- Each optimized lineup now persists the selected coach's CRs, expected score quantiles, matchup team-score forecasts, margin, win probability, source and matchup-validity flag in run artifacts, so the reason for a coach choice can be inspected later.

## Official scoring-rule cross-check

The coach implementation was checked against Dunkest's official coach scoring page:
https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-allenatori

The code's score-margin buckets, overtime win/loss values, 120-point and 95-point bonuses/penalties, and CR-difference coefficient table match the published rules. The Monte Carlo score simulator is still an approximation of overtime scoring, not a possession-by-possession game simulator; its output is a forecast, not a guaranteed result.

## Files changed in this pass

- `src/dunkest/models/coach.py`
- `src/dunkest/optimize/milp.py`
- `src/dunkest/pipeline/optimize.py`
- `src/dunkest/pipeline/season_opener.py`
- `src/dunkest/report/terminal.py`
- `src/dunkest/report/artifacts.py`
- `tests/test_coach_prior_projection.py`
- `tests/test_optimizer_smoke.py`
- `tests/test_pipeline_optimize.py`
- `tests/test_terminal_report.py`

## Verification

- Focused tests after the coach changes: 30 passed; injury/optimizer focused tests: 37 passed.
- Final full suite after all changes: **409 passed in 8.55s** with `-W error::DeprecationWarning`.
- `git diff --check`: passed; Python compilation of all modified modules passed.
- No model training/tuning run, live GW1 forecast run, commit, push, staging, or destructive cleanup was performed.

## Remaining limits

1. The coach score Monte Carlo forecast is supported by prior NBA team scores and current roster-strength estimates when available. If those inputs or the actual opponent coach CR are missing, the coach is now unavailable instead of being assigned an invented neutral score.
2. The 2025/26 historical model comparison has already been examined in previous experiments; it is not a pristine holdout for future model selection.
3. Plusvalenza forecasts remain limited by the sparse official samples available in the local archive. The model does not pretend that missing credit changes or pre-lock market observations exist.
4. Hard OUT/INJURED players are excluded. Players with uncertain participation remain candidates using probability-weighted expected PDK and the calibrated zero-if-absent P10/P50/P90 mixture; the optimizer does not apply the play probability a second time.
5. The correct next improvement is a player-level walk-forward evaluation of the production inference path and a coach-score calibration check using verified score outcomes, not a historical full-lineup backtest or arbitrary weight changes.
