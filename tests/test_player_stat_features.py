import numpy as np
import pandas as pd
import pytest

from dunkest.features.builder import (
    _history_features,
    _attach_inference_team_transitions,
    _normalize_player_opponents,
    _player_opponent_features,
    _rolling_features,
    _row_identity,
    _team_context,
)
from dunkest.features.minutes import expected_minutes_from_history


def _logs():
    return pd.DataFrame([
        {
            "PLAYER_NAME": "Player", "GAME_DATE": "2026-01-01", "OPPONENT": "BOS",
            "TEAM_ABBREVIATION": "NYK", "PDK": 20.0, "MIN": 30.0, "PTS": 12,
            "REB": 10, "AST": 1, "STL": 2, "BLK": 0, "TOV": 1,
            "OREB": 2, "DREB": 8, "FG3M": 3, "FG3A": 6, "FTA": 4, "FTM": 2,
            "FGA": 10,
        },
        {
            "PLAYER_NAME": "Player", "GAME_DATE": "2026-01-03", "OPPONENT": "MIA",
            "TEAM_ABBREVIATION": "NYK", "PDK": 25.0, "MIN": 36.0, "PTS": 20,
            "REB": 11, "AST": 10, "STL": 1, "BLK": 1, "TOV": 2,
            "OREB": 1, "DREB": 10, "FG3M": 4, "FG3A": 8, "FTA": 5, "FTM": 4,
            "FGA": 16,
        },
    ])


def test_game_features_use_only_previous_box_scores():
    original = _logs()
    changed_future = original.copy()
    changed_future.loc[1, "STL"] = 99
    changed_future.loc[1, "FG3M"] = 99

    actual = _rolling_features(original, [3, 5]).iloc[1]
    changed = _rolling_features(changed_future, [3, 5]).iloc[1]

    assert actual["stl_per36_5"] == 2.4
    assert actual["blk_per36_5"] == 0.0
    assert actual["three_point_bonus_mean_5"] == 3.0
    assert actual["pdk_category_bonus_mean_5"] == 5.0
    assert actual["lag1_pdk"] == pytest.approx(20.0)
    assert pd.isna(actual["lag2_pdk"])
    assert actual["lag1_nba_min"] == pytest.approx(30.0)
    assert actual["prev3_nba_min_mean"] == pytest.approx(30.0)
    assert actual["min_trend_3v5"] == pytest.approx(0.0)
    assert actual["min_last_vs_prev5"] == pytest.approx(0.0)
    assert actual["history_games_before_target"] == pytest.approx(1.0)
    assert actual["nba_history_games_before_target"] == pytest.approx(1.0)
    assert changed["stl_per36_5"] == actual["stl_per36_5"]
    assert changed["three_point_bonus_mean_5"] == actual["three_point_bonus_mean_5"]


def test_inference_features_summarize_recent_stat_rates_and_efficiency():
    inference = _rolling_features(_logs(), [3, 5]).iloc[-1]

    assert inference["is_inference"]
    assert inference["stl_per36_5"] == pytest.approx(3 / 66 * 36)
    assert inference["blk_per36_5"] == pytest.approx(1 / 66 * 36)
    assert inference["fg3_pct_5"] == pytest.approx(7 / 14)
    assert inference["ft_pct_5"] == pytest.approx(6 / 9)
    assert inference["three_point_bonus_mean_5"] == 3.5
    assert inference["pdk_category_bonus_mean_5"] == 7.5
    assert inference["lag1_pdk"] == pytest.approx(25.0)
    assert inference["lag2_pdk"] == pytest.approx(20.0)
    assert inference["lag1_nba_min"] == pytest.approx(36.0)
    assert inference["prev3_nba_min_mean"] == pytest.approx(33.0)
    assert inference["history_games_before_target"] == pytest.approx(2.0)
    assert inference["nba_history_games_before_target"] == pytest.approx(2.0)


def test_vectorized_rolling_features_match_history_slice_reference():
    rows = []
    for index in range(8):
        row = _logs().iloc[index % 2].copy()
        row["GAME_DATE"] = pd.Timestamp("2026-01-01") + pd.Timedelta(days=2 * index)
        row["OPPONENT"] = ("BOS", "MIA", "BOS", "NYK")[index % 4]
        row["PDK"] = float(index * 3) if index != 3 else float("nan")
        row["MIN"] = 0.0 if index == 5 else float(20 + index)
        rows.append(row)
    logs = pd.DataFrame(rows).reset_index(drop=True)
    windows = [3, 5]

    actual = _rolling_features(logs, windows)

    for index in range(len(logs)):
        history = logs.iloc[:index]
        expected = _row_identity(logs.iloc[index])
        expected.update(_history_features(history, windows))
        expected["player_opp_pdk_per_min"], expected["player_opp_games"] = (
            _player_opponent_features(history, logs.iloc[index]["OPPONENT"])
        )
        expected["n_games"] = float(index)
        for column, expected_value in expected.items():
            actual_value = actual.loc[index, column]
            if pd.isna(expected_value):
                assert pd.isna(actual_value), column
            elif isinstance(expected_value, (int, float, np.number)):
                assert actual_value == pytest.approx(expected_value), column
            else:
                assert actual_value == expected_value, column

    inference = actual.iloc[-1]
    expected_inference = _history_features(logs, windows)
    expected_inference["player_opp_pdk_per_min"], expected_inference["player_opp_games"] = (
        _player_opponent_features(logs, "")
    )
    for column, expected_value in expected_inference.items():
        actual_value = inference[column]
        if pd.isna(expected_value):
            assert pd.isna(actual_value), column
        else:
            assert actual_value == pytest.approx(expected_value), column


def test_team_transition_and_minute_volatility_features_are_past_only():
    logs = pd.DataFrame([
        {"PLAYER_NAME":"Player", "GAME_DATE":"2026-01-01", "OPPONENT":"BOS", "TEAM_ABBREVIATION":"NYK", "PDK":20.0, "MIN":30.0, "PTS":12, "REB":4, "AST":2},
        {"PLAYER_NAME":"Player", "GAME_DATE":"2026-01-03", "OPPONENT":"MIA", "TEAM_ABBREVIATION":"NYK", "PDK":25.0, "MIN":36.0, "PTS":20, "REB":5, "AST":4},
        {"PLAYER_NAME":"Player", "GAME_DATE":"2026-01-05", "OPPONENT":"BOS", "TEAM_ABBREVIATION":"GSW", "PDK":18.0, "MIN":20.0, "PTS":8, "REB":3, "AST":1},
        {"PLAYER_NAME":"Player", "GAME_DATE":"2026-01-07", "OPPONENT":"MIA", "TEAM_ABBREVIATION":"GSW", "PDK":19.0, "MIN":22.0, "PTS":9, "REB":4, "AST":2},
    ])
    actual = _rolling_features(logs, [3, 5])

    assert actual.loc[0, "team_history_known"] == 0.0
    assert actual.loc[1, "team_history_known"] == 1.0
    assert actual.loc[1, "team_changed_from_previous_game"] == 0.0
    assert actual.loc[2, "team_changed_from_previous_game"] == 1.0
    assert actual.loc[2, "team_games_since_change"] == 0.0
    assert actual.loc[3, "team_changed_from_previous_game"] == 0.0
    assert actual.loc[3, "team_games_since_change"] == 1.0
    assert actual.loc[2, "min_std_5"] == pytest.approx(3.0)
    assert actual.loc[2, "abs_min_last_vs_prev5"] == pytest.approx(abs(36.0 - 33.0))

    inference = actual.iloc[-1:]
    overridden = _attach_inference_team_transitions(inference, logs, {"Player":"BOS"})
    assert overridden.iloc[0]["TEAM_ABBREVIATION"] == "BOS"
    assert overridden.iloc[0]["team_history_known"] == 1.0
    assert overridden.iloc[0]["team_changed_from_previous_game"] == 1.0
    assert overridden.iloc[0]["team_games_since_change"] == 0.0


def test_vectorized_expected_minutes_match_history_slice_reference():
    logs = _logs().iloc[[0, 1, 0, 1, 0]].copy().reset_index(drop=True)
    logs["GAME_DATE"] = [
        pd.Timestamp("2026-01-01") + pd.Timedelta(days=2 * index)
        for index in range(len(logs))
    ]
    logs.loc[2, "MIN"] = float("nan")
    windows = [3, 5]

    actual = expected_minutes_from_history(logs, windows)

    for index in range(len(logs)):
        history = logs.iloc[:index]
        for window in windows:
            expected = history.tail(window)["MIN"].mean() if index else float("nan")
            assert actual.loc[index, f"e_min_{window}"] == pytest.approx(expected, nan_ok=True)
        expected_season = history["MIN"].mean() if index else float("nan")
        assert actual.loc[index, "e_min_season"] == pytest.approx(expected_season, nan_ok=True)

    inference = actual.iloc[-1]
    for window in windows:
        assert inference[f"e_min_{window}"] == pytest.approx(
            logs.tail(window)["MIN"].mean()
        )
    assert inference["e_min_season"] == pytest.approx(logs["MIN"].mean())


def _team_logs():
    rows = []
    for game_id, date, a_pts, b_pts in (
        ("g1", "2026-01-01", 110, 100),
        ("g2", "2026-01-03", 130, 90),
    ):
        rows.extend([
            {
                "Game_ID": game_id, "GAME_DATE": date, "TEAM_ABBREVIATION": "AAA",
                "MATCHUP": "AAA vs. BBB", "PTS": a_pts, "FGA": 90, "FTA": 20,
                "OREB": 10, "DREB": 30, "TOV": 12,
            },
            {
                "Game_ID": game_id, "GAME_DATE": date, "TEAM_ABBREVIATION": "BBB",
                "MATCHUP": "BBB @ AAA", "PTS": b_pts, "FGA": 92, "FTA": 20,
                "OREB": 8, "DREB": 28, "TOV": 10,
            },
        ])
    return pd.DataFrame(rows)


def test_team_matchup_rates_use_only_completed_games():
    logs = _team_logs()
    context = _team_context(logs)
    row = context.loc[
        context.TEAM_ABBREVIATION.eq("AAA") & context.GAME_DATE.eq(pd.Timestamp("2026-01-03"))
    ].iloc[0]

    # Prior game only: opponent points divided by opponent estimated possessions.
    assert row["team_def_rating_mean_5"] == pytest.approx(100 * 100 / 102.8)
    assert row["team_pace_mean_5"] == pytest.approx((100.8 + 102.8) / 2)
    assert row["team_dreb_rate_mean_5"] == pytest.approx(30 / (30 + 8))

    changed_current_result = logs.copy()
    changed_current_result.loc[changed_current_result.Game_ID.eq("g2") & changed_current_result.TEAM_ABBREVIATION.eq("BBB"), "PTS"] = 200
    changed_context = _team_context(changed_current_result)
    changed_row = changed_context.loc[
        changed_context.TEAM_ABBREVIATION.eq("AAA") & changed_context.GAME_DATE.eq(pd.Timestamp("2026-01-03"))
    ].iloc[0]
    assert changed_row["team_def_rating_mean_5"] == row["team_def_rating_mean_5"]


def test_opponents_are_repaired_from_game_id_and_team_matchup():
    player_logs = pd.DataFrame([
        {"PLAYER_NAME": "A", "Game_ID": "g1", "TEAM_ABBREVIATION": "AAA", "OPPONENT": "AAABBB"},
        {"PLAYER_NAME": "B", "Game_ID": "g1", "TEAM_ABBREVIATION": "BBB", "OPPONENT": "BBBAAA"},
    ])
    team_logs = pd.DataFrame([
        {"Game_ID": "g1", "TEAM_ABBREVIATION": "AAA", "MATCHUP": "AAA vs. BBB"},
        {"Game_ID": "g1", "TEAM_ABBREVIATION": "BBB", "MATCHUP": "BBB @ AAA"},
    ])

    repaired = _normalize_player_opponents(player_logs, team_logs)

    assert repaired.OPPONENT.tolist() == ["BBB", "AAA"]


def test_lagged_pdk_features_prefer_verified_official_scores_without_target_leakage():
    logs = _logs().copy()
    logs["PDK_OFFICIAL_VALID"] = [30.0, np.nan]

    actual = _rolling_features(logs, [3, 5])

    # The second game's features may use the first game's verified official
    # score, but never its own current-game target.
    assert actual.loc[1, "pdk_mean_3"] == pytest.approx(30.0)
    assert actual.loc[1, "history_games_before_target"] == pytest.approx(1.0)
    assert actual.iloc[-1]["history_games_before_target"] == pytest.approx(1.0)
    assert actual.iloc[-1]["nba_history_games_before_target"] == pytest.approx(2.0)
    assert actual.loc[1, "target_pdk"] == pytest.approx(25.0)
    assert pd.isna(actual.loc[1, "target_pdk_official"])

    # For inference, use official labels where verified and proxy labels only
    # where the official overlay has no certified score.
    inference = actual.iloc[-1]
    assert inference["pdk_mean_3"] == pytest.approx((30.0 + 25.0) / 2.0)
    assert inference["pdk_season_mean"] == pytest.approx((30.0 + 25.0) / 2.0)


def test_rolling_features_reject_ambiguous_duplicate_player_dates():
    logs = _logs()
    duplicate = pd.concat([logs, logs.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate player/date"):
        _rolling_features(duplicate, [3, 5])


def test_rolling_features_accept_non_unique_dataframe_index_when_dates_are_unique():
    logs = _logs()
    logs.index = [7, 7]
    actual = _rolling_features(logs, [3, 5])
    assert len(actual) == 3
