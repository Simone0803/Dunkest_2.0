from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_history_bins_are_stable_at_boundaries():
    mod = load_script("backtest_dunkest_historical_lineups_gamelevel_actuals_v7.py", "lineup_v7_test")
    values = pd.Series([0, 5, 6, 10, 11, 25, np.nan])
    assert mod.history_bin(values).tolist() == [
        "low_history_0_5", "low_history_0_5", "mid_history_6_10",
        "mid_history_6_10", "established_11_plus", "established_11_plus",
        "low_history_0_5",
    ]


def test_zero_inclusive_training_labels_missing_target_row_as_zero_without_overwriting_lagged_feature():
    mod = load_script("backtest_dunkest_historical_lineups_gamelevel_actuals_v7.py", "lineup_v7_zero_test")
    rows = []
    for rnd in (1, 2):
        players = [("alpha", "Alpha", "BOS"), ("beta", "Beta", "LAL"), ("gamma", "Gamma", "BOS")]
        if rnd == 2:
            players = [p for p in players if p[0] != "beta"]
        for key, name, team in players:
            rows.append({
                "season_id": "9", "round_index": rnd, "player_key": key, "player_name": name,
                "team_code": team, "cr": 10.0, "role": "G", "lagged_role": "G",
                "target_pdk_round_total": {"alpha": 10.0, "beta": 8.0, "gamma": 12.0}[key] if rnd == 1 else {"alpha": 15.0, "gamma": 20.0}[key],
                "source_week": rnd, "source_round": rnd, "history_rounds_before_target": rnd,
                "prev5_pdk_mean": 10.0, "lag1_pdk": 10.0, "lag1_min_avg": 20.0,
                "prev3_pdk_mean": 10.0, "prev10_pdk_mean": 10.0, "prev3_min_mean": 20.0,
                "prev5_min_mean": 20.0, "lag1_plus": 0.0, "lag1_pts_avg": 5.0,
                "lag1_reb_avg": 5.0, "lag1_ast_avg": 2.0, "lag1_stl_avg": 1.0,
                "lag1_blk_avg": 1.0, "lag1_tov_avg": 1.0, "lag1_plus_minus_avg": 0.0,
                "lag1_gp": 1.0, "credit_age_rounds": 1, "prior_round_present": 1,
                "lag1_cr": 10.0, "opp_def_allowed_pts_prev10": 110.0,
                "opp_def_allowed_reb_prev10": 45.0, "opp_def_allowed_ast_prev10": 25.0,
                "target_date": "2022-10-18",
            })
    rows = pd.DataFrame(rows)
    matchups = pd.DataFrame([
        {"season_id": "9", "round_index": 2, "team_code_key": "BOS", "target_opponent": "LAL",
         "opp_def_allowed_pts_prev10": 110.0, "opp_def_allowed_reb_prev10": 45.0, "opp_def_allowed_ast_prev10": 25.0},
        {"season_id": "9", "round_index": 2, "team_code_key": "LAL", "target_opponent": "BOS",
         "opp_def_allowed_pts_prev10": 110.0, "opp_def_allowed_reb_prev10": 45.0, "opp_def_allowed_ast_prev10": 25.0},
    ])
    meta = pd.DataFrame([{"season_id": "9", "round_index": 1, "source_week": 1, "source_round": 1, "target_date": "2022-10-18"},
                         {"season_id": "9", "round_index": 2, "source_week": 2, "source_round": 2, "target_date": "2022-10-20"}])
    out = mod.build_zero_inclusive_training_rows(rows, rows, matchups, meta, ["9"])
    target = out.loc[out["round_index"].eq(2)].set_index("player_key")
    assert set(target.index) == {"alpha", "beta", "gamma"}
    assert target.loc["alpha", "target_pdk_round_total"] == 15.0
    assert target.loc["beta", "target_pdk_round_total"] == 0.0
    assert target.loc["gamma", "target_pdk_round_total"] == 20.0
    assert target.loc["alpha", "lag1_pdk"] == 10.0


def test_groupwise_calibration_shrinks_small_group_toward_global_residual():
    mod = load_script("backtest_dunkest_historical_lineups_gamelevel_actuals_v7.py", "lineup_v7_cal_test")
    frame = pd.DataFrame({"expected": [10.0, 10.0], "lagged_role": ["G", "F"],
                          "history_rounds_before_target": [2, 20]})
    residuals = pd.DataFrame({"role_group": ["G", "G", "F"],
                              "history_group": ["low_history_0_5", "low_history_0_5", "established_11_plus"],
                              "model_residual": [4.0, 4.0, -2.0]})
    corrected = mod.apply_groupwise_calibration(frame, "expected", residuals, "model_residual", "corrected", shrinkage=20.0)
    assert len(corrected) == 2
    assert np.all(np.isfinite(corrected))
    assert corrected[0] > frame.iloc[0]["expected"]
    assert frame.iloc[1]["expected"] < corrected[1] < frame.iloc[1]["expected"] + 2.0


def test_postselection_affine_calibration_is_bounded_and_recovers_linear_relation():
    mod = load_script("calibrate_dunkest_lineup_scores_expanding_v1.py", "lineup_postselection_test")
    x = np.arange(25, dtype=float)
    y = 5.0 + 0.7 * x
    intercept, slope = mod.fit_affine(x, y)
    assert abs(intercept - 5.0) < 1e-8
    assert abs(slope - 0.7) < 1e-8
    intercept2, slope2 = mod.fit_affine(x, 5.0 - 2.0 * x)
    assert slope2 == 0.0
    assert np.isfinite(intercept2)


def test_lineup_score_recovers_coach_team_from_display_label_when_metadata_is_not_a_key():
    from types import SimpleNamespace
    mod = load_script("backtest_dunkest_historical_lineups_gamelevel_actuals_v8.py", "lineup_v8_score_test")
    solution = SimpleNamespace(
        players=pd.DataFrame([{"player_name": "Test Player", "slot": "Captain"}]),
        meta={"selected_coach_team": "Proxy Coach ATL"},
        coach="Proxy Coach ATL",
    )
    player_score, coach_score, total = mod.score_lineup(solution, {"test player": 10.0}, {"ATL": 18.0})
    assert player_score == 10.0 * mod.player_contribution_multiplier(True, False, True)
    assert coach_score == 18.0
    assert total == player_score + 18.0
