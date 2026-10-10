import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge

from dunkest.config import Settings
from dunkest.features.builder import _history_features
from dunkest.models.capital_gain import add_capital_gain_forecasts, fit_capital_gain_model
from dunkest.models.predictor import (
    _fit_projection_weights,
    _lineup_minutes_prior,
    predict_players,
    train_models,
)
from dunkest.uncertainty.quantiles import add_uncertainty_columns


def test_current_roster_competition_scales_expected_minutes_and_role_projection():
    features = pd.DataFrame(
        [
            {"PLAYER_NAME": name, "GAME_DATE": pd.Timestamp("2026-04-01"),
             "min_mean_5": 44.0, "e_min_5": 44.0, "e_min_season": 44.0,
             "pdk_per_min_season": rate}
            for name, rate in (
                ("Guard A", 0.50), ("Guard B", 0.40),
                ("Guard C", 0.30), ("Guard D", 0.25),
            )
        ]
    )
    market = pd.DataFrame(
        [{"player_name": name, "team_code": "BOS", "position": "G", "role": "G", "cr": 16.0}
         for name in ("Guard A", "Guard B", "Guard C", "Guard D")]
    )
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    result = predict_players(Settings(), models, features, market)

    assert (result["competition_scale"] <= 1.0).all()
    assert (result["competition_scale"] < 1.0).any()
    assert result["expected_min"].sum() <= 96.0
    assert (result["expected_min"] < 44.0).all()
    assert result.set_index("player_name").loc["Guard A", "expected_pdk"] > result.set_index("player_name").loc["Guard C", "expected_pdk"]
    assert {"component_minutes_pdk", "component_ensemble_pdk", "component_prior_pdk"}.issubset(result.columns)
    assert (result["expected_pdk"] == result["expected_pdk_before_play_probability"] * result["p_play"]).all()
    assert (result["expected_pdk_conditional"] == result["expected_pdk_before_play_probability"]).all()


def test_lineups_starters_get_a_minutes_prior_and_unavailable_are_zero_play():
    features = pd.DataFrame([
        {"PLAYER_NAME": "Starter", "GAME_DATE": pd.Timestamp("2026-04-01"),
         "min_mean_5": 20.0, "e_min_5": 20.0, "e_min_season": 20.0,
         "pdk_per_min_season": 0.5},
        {"PLAYER_NAME": "Bench", "GAME_DATE": pd.Timestamp("2026-04-01"),
         "min_mean_5": 20.0, "e_min_5": 20.0, "e_min_season": 20.0,
         "pdk_per_min_season": 0.5},
        {"PLAYER_NAME": "Out", "GAME_DATE": pd.Timestamp("2026-04-01"),
         "min_mean_5": 20.0, "e_min_5": 20.0, "e_min_season": 20.0,
         "pdk_per_min_season": 0.5},
    ])
    market = pd.DataFrame([
        {"player_name": "Starter", "team_code": "BOS", "position": "G", "role": "G", "cr": 8.0,
         "lineup_group": "QUINTETTO", "starter": True, "status": "AVAILABLE"},
        {"player_name": "Bench", "team_code": "BOS", "position": "G", "role": "G", "cr": 8.0,
         "lineup_group": "PANCHINA", "starter": False, "status": "AVAILABLE"},
        {"player_name": "Out", "team_code": "BOS", "position": "G", "role": "G", "cr": 8.0,
         "lineup_group": "INDISPONIBILI", "starter": None, "status": "OUT"},
    ])
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    result = predict_players(Settings(), models, features, market).set_index("player_name")

    assert result.loc["Starter", "expected_min"] > result.loc["Bench", "expected_min"]
    assert result.loc["Out", "p_play"] == 0.0


def test_low_credit_rookies_and_bench_players_do_not_get_rotation_minutes():
    features = pd.DataFrame(
        [
            {
                "PLAYER_NAME": "Last Year Starter",
                "GAME_DATE": pd.Timestamp("2026-04-01"),
                "min_mean_5": 32.0,
                "e_min_5": 32.0,
                "e_min_season": 30.0,
                "pdk_per_min_season": 0.5,
                "n_games": 70.0,
            }
        ]
    )
    market = pd.DataFrame(
        [
            {
                "player_name": "Unproven Rookie",
                "team_code": "BOS",
                "position": "F",
                "role": "F",
                "cr": 4.0,
                "lineup_group": "PANCHINA",
                "status": "AVAILABLE",
            },
            {
                "player_name": "Cheap Untagged",
                "team_code": "BOS",
                "position": "F",
                "role": "F",
                "cr": 4.5,
                "lineup_group": "",
                "status": "AVAILABLE",
            },
            {
                "player_name": "Last Year Starter",
                "team_code": "BOS",
                "position": "F",
                "role": "F",
                "cr": 4.5,
                "lineup_group": "PANCHINA",
                "status": "AVAILABLE",
            },
            {
                "player_name": "Sixth Man",
                "team_code": "BOS",
                "position": "F",
                "role": "F",
                "cr": 10.5,
                "lineup_group": "PANCHINA",
                "status": "AVAILABLE",
            },
        ]
    )
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    result = predict_players(Settings(), models, features, market).set_index("player_name")

    assert result.loc["Unproven Rookie", "expected_min"] < 5.0
    assert result.loc["Cheap Untagged", "expected_min"] < 5.0
    assert result.loc["Last Year Starter", "expected_min"] < 6.0
    assert result.loc["Sixth Man", "expected_min"] > 16.0


def test_low_cost_starter_tag_does_not_override_salary_minutes_prior():
    low_cost = _lineup_minutes_prior("QUINTETTO", has_history=False, cr=4.0)
    higher_cost = _lineup_minutes_prior("QUINTETTO", has_history=False, cr=8.0)

    assert low_cost == 7.25
    assert low_cost < higher_cost


def test_player_without_history_does_not_receive_synthetic_pdk_rate():
    market = pd.DataFrame([
        {"player_name": "Unmatched Rookie", "team_code": "BOS", "position": "F", "role": "F",
         "cr": 4.0, "lineup_group": "PANCHINA", "status": "AVAILABLE",
         "official_plusvalenza": 0.3},
    ])
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    result = predict_players(Settings(), models, pd.DataFrame(), market)

    assert pd.isna(result.loc[0, "historical_pdk_per_min"])
    assert result.loc[0, "expected_pdk"] == 0.0
    assert result.loc[0, "official_plusvalenza"] == 0.3


def test_college_rookie_minutes_are_blended_with_cost_and_fade_with_nba_sample():
    market = pd.DataFrame([
        {"player_name": "Rookie", "team_code": "BOS", "position": "F", "role": "F",
         "cr": 8.0, "lineup_group": "", "status": "AVAILABLE"},
    ])
    cost_peers = pd.DataFrame({
        "cr": [8.0] * 10,
        "pdk": [16.0] * 10,
        "min": [24.0] * 10,
        "role": ["F"] * 10,
    })
    rookie_prior = pd.DataFrame([{
        "player_name": "Rookie",
        "college_projected_pdk_per_min": 0.65,
        "nba_rookie_rate_baseline": 0.45,
        "college_prior_base_weight": 0.20,
        "college_projected_minutes_per_game": 30.0,
        "college_minutes_prior_weight": 0.35,
        "college_minutes_cv_mae": 5.8,
        "college_minutes_baseline_cv_mae": 7.3,
    }])
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    rookie = predict_players(
        Settings(), models, pd.DataFrame(), market,
        market_value_history=cost_peers, college_rookie_priors=rookie_prior,
    ).iloc[0]

    assert rookie["college_projected_minutes_per_game"] == 30.0
    assert rookie["college_minutes_prior_weight"] == 0.35
    assert rookie["expected_min"] > 15.0  # CR 8 prior alone is 15 minutes.
    assert rookie["expected_min"] <= 22.0  # Current price/role cap still applies.
    assert rookie["pdk_rate_for_projection"] > 0.45  # Cost peers plus college signal.
    assert abs(rookie["cr_market_pdk_per_min"] - 16.0 / 24.0) < 1e-12
    assert rookie["cr_market_minutes_per_game"] == 24.0
    assert rookie["expected_pdk_conditional"] > 0.0

    after_twelve_games = pd.DataFrame([{
        "PLAYER_NAME": "Rookie",
        "GAME_DATE": pd.Timestamp("2026-11-15"),
        "e_min_5": 20.0,
        "e_min_season": 20.0,
        "pdk_per_min_season": 0.5,
        "n_games": 12.0,
    }])
    updated = predict_players(
        Settings(), models, after_twelve_games, market,
        market_value_history=cost_peers, college_rookie_priors=rookie_prior,
    ).iloc[0]
    assert updated["college_minutes_prior_weight"] == 0.175


def test_high_cr_returner_uses_market_prior_without_mislabeling_history():
    market = pd.DataFrame([
        {"player_name": "Returning Star", "team_code": "IND", "position": "G", "role": "G",
         "cr": 12.5, "lineup_group": "QUINTETTO", "status": "AVAILABLE"},
    ])
    credit_history = pd.DataFrame(
        {
            "cr": [12.0, 12.5, 13.0],
            "pdk": [24.0, 25.0, 26.0],
            "min": [30.0, 32.0, 32.0],
            "role": ["G", "G", "G"],
        }
    )
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    result = predict_players(
        Settings(), models, pd.DataFrame(), market, market_value_history=credit_history
    )

    assert pd.isna(result.loc[0, "historical_pdk_per_min"])
    assert result.loc[0, "projection_source"] == "cr_market_prior"
    assert result.loc[0, "expected_pdk"] > 0.0


def test_season_pdk_rate_is_weighted_by_minutes():
    history = pd.DataFrame({"PDK": [10.0, 20.0], "MIN": [10.0, 40.0]})

    features = _history_features(history, [5])

    assert features["pdk_per_min_season"] == 0.6


def test_ensemble_learns_residuals_and_calibrates_from_temporal_holdout(monkeypatch):
    monkeypatch.setattr(
        "dunkest.models.predictor._model_zoo",
        lambda _settings: {"ridge": Ridge(alpha=1.0)},
    )
    baseline = pd.Series(range(5, 205), dtype=float)
    features = pd.DataFrame({
        "GAME_DATE": pd.date_range("2025-01-01", periods=len(baseline)),
        "target_pdk": baseline + 4.0,
        "target_min": 24.0,
        "expected_pdk_minutes_model": baseline,
    })

    models, prediction = train_models(Settings(), features)
    intervals = add_uncertainty_columns(
        pd.DataFrame({"expected_pdk": [20.0]}),
        residual_std=models["_residual_std"],
        residual_q10=models["_residual_q10"],
        residual_q50=models["_residual_q50"],
        residual_q90=models["_residual_q90"],
    )

    # The first validation fold selects Ridge alpha and is deliberately
    # excluded from weight fitting/calibration; only the next two folds score it.
    assert prediction.notna().sum() == 80
    assert models["_selected_ridge_alpha"] in {0.3, 1.0, 3.0, 10.0, 30.0}
    assert models["_ridge_tuning_fold_excluded_from_oof"] == 0
    assert (prediction.dropna() - features.loc[prediction.notna(), "target_pdk"]).abs().max() < 0.1
    assert models["_residual_q10"] <= models["_residual_q90"]
    assert models["_interval_diagnostics"]
    assert "not independent test-set coverage" in models["_interval_diagnostic_scope"]
    assert any(
        row["dimension"] == "observed_minutes"
        for row in models["_interval_diagnostics"]
    )
    assert intervals.loc[0, "p10"] <= intervals.loc[0, "p50"] <= intervals.loc[0, "p90"]


def test_projection_blend_weights_are_learned_from_out_of_fold_components():
    random = np.random.default_rng(11)
    components = pd.DataFrame(
        {
            "minutes": random.uniform(5.0, 30.0, 100),
            "ensemble": random.uniform(5.0, 30.0, 100),
            "prior": random.uniform(5.0, 30.0, 100),
        }
    )
    target = 0.2 * components["minutes"] + 0.7 * components["ensemble"] + 0.1 * components["prior"]

    weights = _fit_projection_weights(target, components)

    assert abs(weights["minutes"] - 0.2) < 1e-4
    assert abs(weights["ensemble"] - 0.7) < 1e-4
    assert abs(weights["prior"] - 0.1) < 1e-4


def _capital_gain_history(seasons=3, weeks=8, players=25):
    rng = np.random.default_rng(22)
    rows = []
    for season in range(20, 20 + seasons):
        for gameweek in range(1, weeks + 1):
            for _ in range(players):
                cr = float(rng.uniform(4.0, 16.0))
                pdk = float(rng.uniform(2.0, 45.0))
                plus = 0.02 * pdk - 0.01 * cr + 0.03 * pdk / cr + rng.normal(0, .03)
                rows.append({"season_id": season, "gameweek": gameweek,
                             "pdk": pdk, "cr": cr, "plus": plus})
    return pd.DataFrame(rows)


def test_capital_gain_uses_official_score_and_cost_and_walk_forward_residuals():
    history = _capital_gain_history()
    fitted = fit_capital_gain_model(history)
    result = add_capital_gain_forecasts(
        pd.DataFrame({"expected_pdk": [20.0, 12.0], "p10": [18.0, 10.0],
                      "p50": [20.0, 12.0], "p90": [22.0, 14.0], "cr": [8.0, 12.0]}),
        history,
    )
    assert fitted["model"] is not None
    assert fitted["rows"] == len(history)
    assert fitted["mae"] < fitted["baseline_mae"]
    assert result.loc[0, "expected_plusvalenza"] > result.loc[1, "expected_plusvalenza"]
    assert result.loc[0, "plusvalenza_prob_gain"] + result.loc[0, "plusvalenza_prob_loss"] <= 1.0
    assert result.loc[0, "plusvalenza_prob_gain"] + result.loc[0, "plusvalenza_prob_loss"] + result.loc[0, "plusvalenza_prob_flat"] == 1.0
    assert result.loc[0, "plusvalenza_p10"] <= result.loc[0, "plusvalenza_p90"]
    assert np.isfinite(result.loc[0, "expected_plusvalenza"])
    repeated = add_capital_gain_forecasts(
        pd.DataFrame({"expected_pdk": [20.0, 12.0], "p10": [18.0, 10.0],
                      "p50": [20.0, 12.0], "p90": [22.0, 14.0], "cr": [8.0, 12.0]}),
        history,
    )
    pd.testing.assert_frame_equal(result, repeated)


def test_capital_gain_history_is_walk_forward_across_seasons():
    history = _capital_gain_history(seasons=4, weeks=5)
    fitted = fit_capital_gain_model(history)
    assert fitted["rows"] == len(history)
    assert len(fitted["residuals"]) > 0


def test_capital_gain_does_not_extrapolate_beyond_historical_cost_support():
    history = _capital_gain_history()
    forecasts = pd.DataFrame({"expected_pdk": [45.0], "p10": [40.0], "p50": [45.0],
                              "p90": [50.0], "cr": [30.0]})
    result = add_capital_gain_forecasts(forecasts, history)
    assert pd.isna(result.loc[0, "expected_plusvalenza"])
    assert not result.loc[0, "plusvalenza_cost_supported"]
    assert result.loc[0, "plusvalenza_source"] == "outside_cost_support"
