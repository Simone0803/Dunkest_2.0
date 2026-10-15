import pandas as pd
import warnings

from dunkest.config import Settings
from dunkest.data import access
from dunkest.models.coach import predict_coach_points


def test_coach_opener_uses_prior_team_coach_score_when_matchup_is_missing():
    coaches = pd.DataFrame(
        [
            {"coach": "Strong prior", "team": "BOS", "coach_cr": 8.0,
             "opponent_coach_cr": float("nan"), "prior_coach_pdk": 12.5},
            {"coach": "Weak prior", "team": "NYK", "coach_cr": 6.0,
             "opponent_coach_cr": float("nan"), "prior_coach_pdk": -3.0},
        ]
    )

    result = predict_coach_points(coaches).set_index("coach")

    assert result.loc["Strong prior", "expected_coach_pdk"] == 12.5
    assert result.loc["Weak prior", "expected_coach_pdk"] == -3.0


def test_gameweek_one_does_not_recommend_coaches_from_historical_team_prior():
    coaches = pd.DataFrame([{
        "coach": "Strong last season", "team": "BOS", "coach_cr": 8.0,
        "opponent_coach_cr": float("nan"), "prior_coach_pdk": 20.0,
    }])

    result = predict_coach_points(coaches, gameweek=1).iloc[0]

    assert result.expected_coach_pdk == 0.0
    assert result.coach_projection_source == "no_verified_matchup"
    assert not result.matchup_projection_available


def test_opening_schedule_without_team_logs_keeps_matchup_but_refuses_fake_score_forecast():
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "BOS", "coach_cr": 9.0, "opponent_coach_cr": 7.0},
        {"coach": "Coach B", "team": "NYK", "coach_cr": 7.0, "opponent_coach_cr": 9.0},
    ])
    schedule = pd.DataFrame([{
        "GAME_DATE": "2026-10-20T23:00:00Z",
        "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK",
        "mapping_verified": True,
    }])

    result = predict_coach_points(
        coaches, team_logs=None, upcoming_schedule=schedule, gameweek=1
    ).set_index("team")

    assert result.loc["BOS", "opponent"] == "NYK"
    assert result.loc["NYK", "opponent"] == "BOS"
    assert not result["matchup_projection_available"].any()
    assert result["coach_projection_source"].eq("missing_team_history").all()
    assert result["expected_coach_pdk"].eq(0.0).all()
    assert result["expected_team_pts"].isna().all()


def test_historical_team_results_create_distinct_coach_point_priors(monkeypatch):
    monkeypatch.setattr(
        access.nba,
        "fetch_schedule",
        lambda settings: pd.DataFrame([
            {"HOME_TEAM": "BOS", "AWAY_TEAM": "NYK", "PTS": 120, "PLUS_MINUS": 20}
        ]),
    )
    coaches = {"BOS": ("Coach A", 8.0), "NYK": ("Coach B", 6.0)}

    result = access._historical_coach_scores(Settings(), coaches)

    assert result["BOS"] > result["NYK"]


def test_coach_price_does_not_stand_in_for_team_strength_without_matchup_data():
    coaches = pd.DataFrame(
        [
            {"coach": "Higher priced", "team": "BOS", "coach_cr": 10.0,
             "opponent_coach_cr": float("nan")},
            {"coach": "Lower priced", "team": "NYK", "coach_cr": 6.0,
             "opponent_coach_cr": float("nan")},
        ]
    )

    result = predict_coach_points(coaches).set_index("coach")

    assert pd.isna(result.loc["Higher priced", "expected_margin"])
    assert pd.isna(result.loc["Lower priced", "expected_margin"])
    assert result.loc["Higher priced", "expected_coach_pdk"] == 0.0
    assert result.loc["Lower priced", "expected_coach_pdk"] == 0.0


def test_disabling_coach_model_returns_neutral_projection():
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "BOS", "coach_cr": 9.0, "prior_coach_pdk": 15.0},
        {"coach": "Coach B", "team": "NYK", "coach_cr": 6.0, "prior_coach_pdk": -5.0},
    ])

    result = predict_coach_points(coaches, use_model=False)

    for column in ("expected_coach_pdk", "p10_coach_pdk", "p50_coach_pdk", "p90_coach_pdk"):
        assert result[column].eq(0.0).all()


def test_cheap_coach_gets_matchup_projection_against_weak_defense():
    coaches = pd.DataFrame(
        [
            {"coach": "Value coach", "team": "BOS", "coach_cr": 6.0, "prior_coach_pdk": 2.0},
            {"coach": "Premium coach", "team": "NYK", "coach_cr": 9.0, "prior_coach_pdk": 2.0},
        ]
    )
    team_logs = pd.DataFrame(
        [
            {"Game_ID": "g1", "TEAM_ABBREVIATION": "BOS", "PTS": 120, "GAME_DATE": "2026-04-01"},
            {"Game_ID": "g1", "TEAM_ABBREVIATION": "NYK", "PTS": 100, "GAME_DATE": "2026-04-01"},
            {"Game_ID": "g2", "TEAM_ABBREVIATION": "BOS", "PTS": 120, "GAME_DATE": "2026-04-03"},
            {"Game_ID": "g2", "TEAM_ABBREVIATION": "NYK", "PTS": 100, "GAME_DATE": "2026-04-03"},
        ]
    )
    schedule = pd.DataFrame(
        [
            {"GAME_DATE": "2026-10-05", "HOME_TEAM": "BOS", "AWAY_TEAM": "NOP", "NBA_WEEK_NUMBER": 0, "GAME_STATUS": 1},
            {"GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK", "NBA_WEEK_NUMBER": 1, "GAME_STATUS": 1},
        ]
    )

    result = predict_coach_points(coaches, team_logs, schedule).set_index("coach")

    assert result.loc["Value coach", "opponent"] == "NYK"
    assert result.loc["Value coach", "matchup_date"] == pd.Timestamp("2026-10-20")
    assert result.loc["Value coach", "expected_team_pts"] > result.loc["Value coach", "expected_opp_pts"]
    assert result.loc["Value coach", "expected_coach_pdk"] > result.loc["Premium coach", "expected_coach_pdk"]


def test_coach_matchup_adjusts_for_projected_roster_strength():
    coaches = pd.DataFrame(
        [
            {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0, "opponent_coach_cr": 6.0},
            {"coach": "Coach B", "team": "NYK", "coach_cr": 6.0, "opponent_coach_cr": 8.0},
        ]
    )
    player_logs = pd.DataFrame(
        [
            {"GAME_ID": f"g{game_number}", "TEAM_ABBREVIATION": team, "PDK": pdk_total}
            for game_number in range(20)
            for team, pdk_total in (("BOS", 100.0), ("NYK", 80.0))
        ]
    )
    team_logs = pd.DataFrame(
        [
            {"Game_ID": f"g{game_number}", "TEAM_ABBREVIATION": team, "PTS": points}
            | {"GAME_DATE": pd.Timestamp("2026-01-01") + pd.Timedelta(days=game_number)}
            for game_number in range(20)
            for team, points in (("BOS", 120.0), ("NYK", 100.0))
        ]
    )
    schedule = pd.DataFrame(
        [{"GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK", "NBA_WEEK_NUMBER": 1}]
    )
    player_forecasts = pd.DataFrame(
        [
            {"team": "BOS", "expected_pdk": 120.0},
            {"team": "NYK", "expected_pdk": 80.0},
        ]
    )

    historical_only = predict_coach_points(coaches, team_logs, schedule)
    roster_adjusted = predict_coach_points(
        coaches, team_logs, schedule, player_logs, player_forecasts
    )

    historical_bos = historical_only.loc[historical_only.team.eq("BOS"), "expected_team_pts"].iloc[0]
    adjusted_bos = roster_adjusted.loc[roster_adjusted.team.eq("BOS"), "expected_team_pts"].iloc[0]
    bos_adjustment = roster_adjusted.loc[roster_adjusted.team.eq("BOS"), "team_roster_points_adjustment"].iloc[0]
    opponent_adjustment = roster_adjusted.loc[roster_adjusted.team.eq("BOS"), "opponent_roster_points_adjustment"].iloc[0]
    assert adjusted_bos == historical_bos + bos_adjustment
    assert bos_adjustment > 2.0
    assert opponent_adjustment < -2.0
    assert abs(bos_adjustment) <= 6.0
    assert abs(opponent_adjustment) <= 6.0
    assert roster_adjusted.loc[roster_adjusted.team.eq("BOS"), "net_roster_strength_adjustment"].iloc[0] == bos_adjustment - opponent_adjustment
    assert roster_adjusted.loc[roster_adjusted.team.eq("BOS"), "team_roster_projection_available"].iloc[0]
    assert roster_adjusted.loc[roster_adjusted.team.eq("BOS"), "opponent_roster_projection_available"].iloc[0]


def test_team_profiles_weight_recent_form_and_shrink_team_volatility():
    from dunkest.models.coach import _team_profiles

    rows = []
    for game_number in range(20):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=game_number)
        points_a = 100.0 if game_number < 19 else 160.0
        rows.extend([
            {"team": "A", "team_points": points_a, "opponent_points": 110.0,
             "game_date": date},
            {"team": "B", "team_points": 110.0, "opponent_points": points_a,
             "game_date": date},
        ])

    profile, score_sds, _ = _team_profiles(pd.DataFrame(rows))
    unweighted_a_mean = float(pd.DataFrame(rows).loc[
        pd.DataFrame(rows)["team"].eq("A"), "team_points"
    ].mean())

    assert profile.loc["A", "offense"] > unweighted_a_mean
    assert profile.loc["A", "offense"] < 160.0  # recent signal remains shrunk
    assert 8.0 <= score_sds["A"] <= 18.0
    assert score_sds["A"] > score_sds["B"]


def test_matchup_projection_uses_different_team_score_volatility():
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0, "opponent_coach_cr": 7.0},
        {"coach": "Coach B", "team": "NYK", "coach_cr": 7.0, "opponent_coach_cr": 8.0},
    ])
    logs = []
    for game_number in range(20):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=game_number)
        bos_points = 100.0 if game_number < 19 else 160.0
        logs.extend([
            {"Game_ID": f"g{game_number}", "TEAM_ABBREVIATION": "BOS",
             "PTS": bos_points, "GAME_DATE": date},
            {"Game_ID": f"g{game_number}", "TEAM_ABBREVIATION": "NYK",
             "PTS": 110.0, "GAME_DATE": date},
        ])
    schedule = pd.DataFrame([
        {"GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK", "WEEK_NUMBER": 1}
    ])

    result = predict_coach_points(coaches, pd.DataFrame(logs), schedule).set_index("team")

    assert result.loc["BOS", "team_score_sd"] > result.loc["BOS", "opponent_score_sd"]
    assert result.loc["NYK", "opponent_score_sd"] > result.loc["NYK", "team_score_sd"]
    assert result.loc["BOS", "p10_coach_pdk"] <= result.loc["BOS", "p50_coach_pdk"]
    assert result.loc["BOS", "p50_coach_pdk"] <= result.loc["BOS", "p90_coach_pdk"]


def test_efficiency_matchup_uses_opponent_points_allowed_not_own_points():
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0, "opponent_coach_cr": 8.0},
        {"coach": "Coach B", "team": "BKN", "coach_cr": 8.0, "opponent_coach_cr": 8.0},
    ])
    logs = []
    for game_number in range(20):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=game_number)
        logs.extend([
            {"Game_ID": f"g{game_number}", "TEAM_ABBREVIATION": "BOS", "PTS": 120.0,
             "FGA": 100.0, "FTA": 0.0, "OREB": 0.0, "TOV": 0.0, "GAME_DATE": date},
            {"Game_ID": f"g{game_number}", "TEAM_ABBREVIATION": "BKN", "PTS": 100.0,
             "FGA": 100.0, "FTA": 0.0, "OREB": 0.0, "TOV": 0.0, "GAME_DATE": date},
        ])
    schedule = pd.DataFrame([
        {"GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "BKN", "NBA_WEEK_NUMBER": 1}
    ])

    result = predict_coach_points(coaches, pd.DataFrame(logs), schedule).set_index("team")

    assert result.loc["BOS", "expected_team_pts"] > result.loc["BOS", "expected_opp_pts"]
    assert result.loc["BOS", "expected_team_pts"] == result.loc["BKN", "expected_opp_pts"]


def test_current_roster_adjustment_applies_when_efficiency_data_is_available():
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0, "opponent_coach_cr": 8.0},
        {"coach": "Coach B", "team": "BKN", "coach_cr": 8.0, "opponent_coach_cr": 8.0},
    ])
    team_rows = []
    player_rows = []
    for game_number in range(20):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=game_number)
        game_id = f"g{game_number}"
        for team, points, pdk in (
            ("BOS", 100.0 + game_number, 100.0 + game_number),
            ("BKN", 90.0 + game_number, 80.0 + game_number),
        ):
            team_rows.append({
                "Game_ID": game_id, "TEAM_ABBREVIATION": team, "PTS": points,
                "FGA": 100.0, "FTA": 0.0, "OREB": 0.0, "TOV": 0.0,
                "GAME_DATE": date,
            })
            player_rows.append({
                "GAME_ID": game_id, "TEAM_ABBREVIATION": team, "PDK": pdk,
            })
    schedule = pd.DataFrame([
        {"GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "BKN", "NBA_WEEK_NUMBER": 1}
    ])
    forecasts = pd.DataFrame([
        {"team": "BOS", "expected_pdk": 120.0},
        {"team": "BKN", "expected_pdk": 99.5},
    ])

    baseline = predict_coach_points(coaches, pd.DataFrame(team_rows), schedule).set_index("team")
    current_roster = predict_coach_points(
        coaches, pd.DataFrame(team_rows), schedule,
        pd.DataFrame(player_rows), forecasts,
    ).set_index("team")

    adjustment = current_roster.loc["BOS", "team_roster_points_adjustment"]
    assert adjustment > 0.0
    assert current_roster.loc["BOS", "expected_team_pts"] == baseline.loc["BOS", "expected_team_pts"] + adjustment
    assert abs(
        current_roster.loc["BOS", "win_probability_before_roster_adjustment"]
        - baseline.loc["BOS", "win_probability"]
    ) < 1e-9
    assert abs(
        current_roster.loc["BOS", "win_probability"]
        + current_roster.loc["BKN", "win_probability"] - 1.0
    ) < 1e-9


def test_constant_game_scores_use_neutral_correlation_without_runtime_warning():
    coaches = pd.DataFrame(
        [
            {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0, "opponent_coach_cr": 6.0},
            {"coach": "Coach B", "team": "NYK", "coach_cr": 6.0, "opponent_coach_cr": 8.0},
        ]
    )
    team_logs = pd.DataFrame(
        [
            {"Game_ID": f"g{n}", "TEAM_ABBREVIATION": team, "PTS": 100.0}
            for n in range(10)
            for team in ("BOS", "NYK")
        ]
    )
    schedule = pd.DataFrame(
        [{"GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK", "NBA_WEEK_NUMBER": 1}]
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = predict_coach_points(coaches, team_logs, schedule)

    assert result["score_correlation"].eq(0.1).all()


def test_market_opponent_selects_matching_game_over_first_week_fixture():
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "A", "coach_cr": 8.0,
         "opponent": "B", "opponent_coach_cr": 8.0, "date": "2026-10-22"},
        {"coach": "Coach B", "team": "B", "coach_cr": 8.0,
         "opponent": "A", "opponent_coach_cr": 8.0, "date": "2026-10-22"},
        {"coach": "Coach C", "team": "C", "coach_cr": 8.0,
         "opponent": "A", "opponent_coach_cr": 8.0, "date": "2026-10-20"},
    ])
    logs = []
    for number in range(12):
        date = pd.Timestamp("2026-03-01") + pd.Timedelta(days=number)
        teams = ("A", "C") if number < 6 else ("A", "B")
        for team in teams:
            logs.append({
                "Game_ID": f"g{number}", "TEAM_ABBREVIATION": team,
                "PTS": 115.0, "GAME_DATE": date,
            })
    schedule = pd.DataFrame([
        {"nba_game_id": "ac", "game_datetime_utc": "2026-10-20T00:00:00Z", "home_team": "A", "away_team": "C", "dunkest_gameweek": 1, "dunkest_turn": 1, "fantasy_eligible": False},
        {"nba_game_id": "ab", "game_datetime_utc": "2026-10-22T00:00:00Z", "home_team": "A", "away_team": "B", "dunkest_gameweek": 1, "dunkest_turn": 2, "fantasy_eligible": True},
    ])

    result = predict_coach_points(coaches, pd.DataFrame(logs), schedule, gameweek=1)
    coach_a = result.loc[result.team.eq("A")].iloc[0]

    assert coach_a.opponent == "B"
    assert pd.Timestamp(coach_a.matchup_date).date() == pd.Timestamp("2026-10-22").date()
    assert coach_a.nba_game_id == "ab"
    assert coach_a.dunkest_turn == 2


def test_all_zero_team_forecasts_do_not_collapse_historical_coach_strength():
    from dunkest.models.coach import _roster_point_adjustments

    player_logs = pd.DataFrame([
        {"GAME_ID": f"g{n}", "TEAM_ABBREVIATION": team, "PDK": score}
        for n in range(20)
        for team, score in (("OKC", 110.0), ("BKN", 85.0))
    ])
    team_logs = pd.DataFrame([
        {"Game_ID": f"g{n}", "TEAM_ABBREVIATION": team, "PTS": points}
        for n in range(20)
        for team, points in (("OKC", 120.0), ("BKN", 105.0))
    ])
    forecasts = pd.DataFrame([
        {"team": "OKC", "expected_pdk": 0.0},
        {"team": "BKN", "expected_pdk": 90.0},
    ])

    adjustments = _roster_point_adjustments(player_logs, team_logs, forecasts)

    assert "OKC" not in adjustments


def test_coach_simulation_never_returns_tied_final_scores():
    from dunkest.models.coach import _simulate_matchup_scores

    args = (108.0, 108.0, 14.0, 14.0, 0.15, "BOS-NYK", 0.0)
    team_a, opponent_a, overtime_a = _simulate_matchup_scores(*args, draws=4096)
    team_b, opponent_b, overtime_b = _simulate_matchup_scores(*args, draws=4096)

    assert (team_a == opponent_a).sum() == 0
    assert (team_b == opponent_b).sum() == 0
    assert (team_a == team_b).all()
    assert (opponent_a == opponent_b).all()
    assert (overtime_a == overtime_b).all()
    assert overtime_a.any()  # ties in rounded regulation-score draws force overtime


def test_coach_synthetic_matchup_uses_fallback_date_when_primary_date_is_nullable():
    coaches = pd.DataFrame([{
        "coach": "Coach A", "team": "BOS", "opponent": "NYK", "coach_cr": 8.0,
        "opponent_coach_cr": 7.0, "date": pd.NA, "matchup_date": "2026-10-20",
    }])
    logs = pd.DataFrame([
        {"Game_ID": "a1", "TEAM_ABBREVIATION": "BOS", "PTS": 115.0, "GAME_DATE": "2026-04-01"},
        {"Game_ID": "a1", "TEAM_ABBREVIATION": "NYK", "PTS": 105.0, "GAME_DATE": "2026-04-01"},
    ])
    result = predict_coach_points(coaches, team_logs=logs, upcoming_schedule=pd.DataFrame())

    assert result.loc[0, "matchup_date"] == pd.Timestamp("2026-10-20")


def test_missing_opponent_coach_credit_is_not_imputed_from_selected_coach():
    coaches = pd.DataFrame([{
        "coach": "Coach A", "team": "BOS", "coach_cr": 10.0,
        "opponent": "NYK", "opponent_coach_cr": float("nan"),
    }])
    team_logs = pd.DataFrame([
        {"Game_ID": f"g{i}", "TEAM_ABBREVIATION": team, "PTS": pts,
         "GAME_DATE": pd.Timestamp("2026-03-01") + pd.Timedelta(days=i)}
        for i in range(12) for team, pts in (("BOS", 120.0), ("NYK", 105.0))
    ])
    schedule = pd.DataFrame([{
        "GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK",
        "NBA_WEEK_NUMBER": 1,
    }])

    result = predict_coach_points(coaches, team_logs, schedule, gameweek=1).iloc[0]

    assert pd.isna(result.opponent_coach_cr)
    assert result.coach_projection_source == "missing_opponent_coach_cr"
    assert not result.matchup_projection_available
    assert result.expected_coach_pdk == 0.0
