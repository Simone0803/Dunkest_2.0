import numpy as np
import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.models.multiseason_training import adapt_certified_training_rows


def _source():
    rows = []
    for season, sid, date in [("2020-21", "5", "2020-12-22"), ("2024-25", "19", "2024-10-22"), ("2025-26", "25", "2025-10-22")]:
        rows.append({
            "season_label": season, "season_id": sid, "game_date": date,
            "gameId": f"{sid}-game", "dunkest_player_id": "p1",
            "dunkest_player_name": "Test Player", "target_pdk": 12.5,
            "history_games_before_target": 4, "lag1_pdk": 10.0,
            "lag2_pdk": 9.0, "lag3_pdk": 8.0, "lag4_pdk": 7.0,
            "lag5_pdk": 6.0, "prev3_pdk_mean": 9.0,
            "prev5_pdk_mean": 8.0, "prev10_pdk_mean": 8.0,
            "prev5_pdk_std": 1.5, "prev5_nba_min_mean": 30.0,
            "prev5_nba_pts_mean": 20.0, "prev5_nba_reb_mean": 5.0,
            "prev5_nba_ast_mean": 4.0, "rest_days_from_nba_logs": 2,
            "nba_history_games_before_target": 11, "prev3_nba_min_mean": 28.0,
            "lag1_nba_min": 32.0, "lag2_nba_min": 30.0, "lag3_nba_min": 22.0,
            "lag1_nba_pts": 21.0, "lag2_nba_pts": 19.0, "lag3_nba_pts": 14.0,
            "prev3_nba_pts_mean": 18.0, "lag1_nba_reb": 6.0, "lag2_nba_reb": 5.0,
            "lag3_nba_reb": 4.0, "prev3_nba_reb_mean": 5.0,
            "lag1_nba_ast": 5.0, "lag2_nba_ast": 4.0, "lag3_nba_ast": 3.0,
            "prev3_nba_ast_mean": 4.0, "opponentTeamPosition": "visitor",
            "nba_match_status": "matched_player_date_opponent",
        })
    return pd.DataFrame(rows)


def test_multi_season_adapter_uses_certified_seasons_and_past_only_columns():
    out = adapt_certified_training_rows(_source(), minimum_rows=1)
    assert out["season_label"].tolist() == ["2020-21", "2024-25"]
    assert out["target_pdk_official"].tolist() == [12.5, 12.5]
    assert out["pdk_mean_3"].tolist() == [9.0, 9.0]
    assert out["lag1_pdk"].tolist() == [10.0, 10.0]
    assert out["lag1_nba_min"].tolist() == [32.0, 32.0]
    assert out["prev3_nba_min_mean"].tolist() == [28.0, 28.0]
    assert out["pdk_trend_3v10"].tolist() == [1.0, 1.0]
    assert out["min_trend_3v5"].tolist() == [-2.0, -2.0]
    assert out["min_last_vs_prev5"].tolist() == [2.0, 2.0]
    assert out["n_games"].tolist() == [11.0, 11.0]
    assert out["expected_pdk_minutes_model"].eq(0.0).all()
    assert out["_training_sample_weight"].eq(1.25).all()
    assert out["min_mean_10"].isna().all()
    assert out["fg3_pct_5"].isna().all()
    assert out["is_inference"].eq(False).all()
    assert "target_pdk_official" not in {
        "pdk_mean_3", "pdk_mean_5", "pdk_mean_10", "pts_mean_5"
    }


def test_multi_season_adapter_joins_minutes_as_label_and_derives_team_transition_features():
    source = _source()
    source["nba_GAME_ID"] = ["nba-5", "nba-19", "nba-25"]
    source["nba_PLAYER_ID"] = [123, 123, 123]
    source["nba_TEAM_ABBREVIATION"] = ["NYK", "GSW", "GSW"]
    labels = pd.DataFrame({
        "nba_GAME_ID": ["nba-5", "nba-19", "nba-25"],
        "nba_PLAYER_ID": [123, 123, 123],
        "nba_MIN": [20.0, 32.0, 30.0],
        "nba_match_status": ["matched_player_date_opponent"] * 3,
    })

    out = adapt_certified_training_rows(source, minimum_rows=1, minutes_labels=labels)

    assert out["season_label"].tolist() == ["2020-21", "2024-25"]
    assert out["target_min"].tolist() == [20.0, 32.0]
    assert out["team_history_known"].tolist() == [0.0, 1.0]
    assert out["team_changed_from_previous_game"].tolist() == [0.0, 1.0]
    assert out["team_games_since_change"].tolist() == [0.0, 0.0]
    assert "target_min" not in __import__("dunkest.models.predictor", fromlist=["FEATURE_COLS"]).FEATURE_COLS


def test_multi_season_adapter_fails_closed_on_duplicate_game_keys():
    source = _source()
    source = pd.concat([source.iloc[[0]], source.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate season/player/game"):
        adapt_certified_training_rows(source, minimum_rows=1)


def test_multi_season_adapter_fails_closed_on_missing_required_schema():
    with pytest.raises(ValueError, match="missing required columns"):
        adapt_certified_training_rows(pd.DataFrame({"season_label": ["2024-25"]}))


def test_multi_season_adapter_can_include_2025_26_only_for_explicit_test_folds():
    out = adapt_certified_training_rows(_source(), minimum_rows=1, include_2025_26=True)
    assert out["season_label"].tolist() == ["2020-21", "2024-25", "2025-26"]


def test_current_season_training_appends_only_observed_official_labels():
    from dunkest.models.multiseason_training import _append_current_official_rows

    settings = Settings(nba_season_start="2026-10-20")
    historical = pd.DataFrame([{
        "GAME_DATE": pd.Timestamp("2024-10-22"), "PLAYER_ID": "old-player",
        "GAME_ID": "old-game", "target_pdk": 11.0,
        "target_pdk_official": 11.0, "expected_pdk_minutes_model": 0.0,
        "_training_sample_weight": 1.25, "is_inference": False,
        "pdk_mean_3": 10.0, "pdk_mean_15": np.nan,
    }])
    current = pd.DataFrame([
        {
            "GAME_DATE": "2026-10-21", "PLAYER_ID": "current-player",
            "GAME_ID": "official-game", "target_pdk": 12.0,
            "target_pdk_official": 12.0, "expected_pdk_minutes_model": 18.0,
            "_training_sample_weight": 1.0, "is_inference": False,
            "pdk_mean_3": 9.0, "pdk_mean_15": 20.0,
        },
        {
            "GAME_DATE": "2026-10-21", "PLAYER_ID": "proxy-player",
            "GAME_ID": "proxy-game", "target_pdk": 20.0,
            "target_pdk_official": np.nan, "expected_pdk_minutes_model": 21.0,
            "_training_sample_weight": 1.0, "is_inference": False,
            "pdk_mean_3": 19.0, "pdk_mean_15": 21.0,
        },
        {
            "GAME_DATE": "2026-10-22", "PLAYER_ID": "future-player",
            "GAME_ID": "inference-game", "target_pdk": np.nan,
            "target_pdk_official": 99.0, "expected_pdk_minutes_model": 25.0,
            "_training_sample_weight": 1.0, "is_inference": True,
            "pdk_mean_3": 22.0, "pdk_mean_15": 23.0,
        },
        {
            "GAME_DATE": "2025-11-01", "PLAYER_ID": "holdout-player",
            "GAME_ID": "holdout-game", "target_pdk": 14.0,
            "target_pdk_official": 14.0, "expected_pdk_minutes_model": 16.0,
            "_training_sample_weight": 1.0, "is_inference": False,
            "pdk_mean_3": 13.0, "pdk_mean_15": 14.0,
        },
    ])

    combined, current_count = _append_current_official_rows(historical, current, settings)

    assert current_count == 1
    assert set(combined["PLAYER_ID"]) == {"old-player", "current-player"}
    assert combined["expected_pdk_minutes_model"].eq(0.0).all()
    assert combined.loc[combined["PLAYER_ID"].eq("current-player"), "_training_sample_weight"].item() == 1.0
    assert combined["pdk_mean_15"].isna().all()


def test_current_season_training_does_not_append_proxy_only_rows():
    from dunkest.models.multiseason_training import _append_current_official_rows

    settings = Settings(nba_season_start="2026-10-20")
    historical = pd.DataFrame([{
        "GAME_DATE": pd.Timestamp("2024-10-22"), "PLAYER_ID": "old-player",
        "GAME_ID": "old-game", "target_pdk": 11.0,
        "target_pdk_official": 11.0, "expected_pdk_minutes_model": 0.0,
        "_training_sample_weight": 1.0, "pdk_mean_3": 10.0,
    }])
    current = pd.DataFrame([{
        "GAME_DATE": "2026-10-21", "PLAYER_ID": "proxy-player",
        "GAME_ID": "proxy-game", "target_pdk": 20.0,
        "target_pdk_official": np.nan, "expected_pdk_minutes_model": 21.0,
        "_training_sample_weight": 1.0, "is_inference": False,
        "pdk_mean_3": 19.0,
    }])

    combined, current_count = _append_current_official_rows(historical, current, settings)

    assert current_count == 0
    assert combined["PLAYER_ID"].tolist() == ["old-player"]
