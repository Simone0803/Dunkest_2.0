import pandas as pd
import pytest

from dunkest.evaluation.coach_shadow import compare_coach_roster_variants


def _inputs():
    team_rows = []
    player_rows = []
    for game_number in range(20):
        game_id = f"hist-{game_number}"
        game_date = pd.Timestamp("2026-10-01", tz="UTC") + pd.Timedelta(days=game_number)
        for team, pdk, points in (
            ("BOS", 95.0 + game_number, 108.0 + game_number),
            ("NYK", 85.0 + game_number, 103.0 + game_number),
        ):
            team_rows.append({
                "Game_ID": game_id, "TEAM_ABBREVIATION": team,
                "PTS": points, "GAME_DATE": game_date,
            })
            player_rows.append({
                "GAME_ID": game_id, "TEAM_ABBREVIATION": team,
                "PDK": pdk, "GAME_DATE": game_date,
            })
    team_logs = pd.DataFrame(team_rows)
    player_logs = pd.DataFrame(player_rows)
    coaches = pd.DataFrame([
        {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0, "opponent_coach_cr": 6.0},
        {"coach": "Coach B", "team": "NYK", "coach_cr": 6.0, "opponent_coach_cr": 8.0},
    ])
    schedule = pd.DataFrame([{
        "nba_game_id": "future-game-1",
        "game_datetime_utc": "2026-10-25T23:00:00Z",
        "home_team": "BOS", "away_team": "NYK",
        "dunkest_gameweek": 3, "fantasy_eligible": True,
        "mapping_verified": True, "home_team_eligible": True,
        "away_team_eligible": True,
    }])
    forecasts = pd.DataFrame([
        {"team": "BOS", "expected_pdk": 140.0},
        {"team": "NYK", "expected_pdk": 70.0},
    ])
    return coaches, team_logs, player_logs, schedule, forecasts


def _run(inputs):
    coaches, team_logs, player_logs, schedule, forecasts = inputs
    return compare_coach_roster_variants(
        coaches,
        team_logs=team_logs,
        upcoming_schedule=schedule,
        player_logs=player_logs,
        player_forecasts=forecasts,
        season_id="26",
        gameweek=3,
        forecast_timestamp_utc="2026-10-25T09:00:00Z",
        current_season_start_utc="2026-10-01T00:00:00Z",
        shrinkage_prior_games=8.0,
    )


def test_shadow_variants_share_stable_identity_and_never_mark_solver_input():
    result = _run(_inputs())

    assert set(result["variant"]) == {
        "production_current", "no_roster_adjustment", "roster_shrinkage"
    }
    assert result.groupby("comparison_observation_id")["variant"].nunique().eq(3).all()
    assert result["nba_game_id"].eq("future-game-1").all()
    assert result["matchup_identity_verified"].all()
    assert not result["optimizer_input"].any()
    assert result[["expected_margin", "win_probability", "expected_coach_pdk"]].notna().all().all()


def test_shrinkage_uses_current_season_paired_sample_and_coverage():
    result = _run(_inputs())
    rows = result.loc[result["variant"].eq("roster_shrinkage")]

    assert rows["team_current_season_paired_games"].eq(20).all()
    assert rows["team_current_season_pair_coverage"].eq(1.0).all()
    assert rows["team_shrinkage_weight"].eq(20 / 28).all()


def test_same_day_and_future_boxscores_are_excluded_before_variant_calls():
    inputs = list(_inputs())
    team_logs = inputs[1].copy()
    player_logs = inputs[2].copy()
    team_logs = pd.concat([team_logs, pd.DataFrame([
        {"Game_ID": "same-day", "TEAM_ABBREVIATION": "BOS", "PTS": 150, "GAME_DATE": "2026-10-25"},
        {"Game_ID": "same-day", "TEAM_ABBREVIATION": "NYK", "PTS": 80, "GAME_DATE": "2026-10-25"},
    ])], ignore_index=True)
    player_logs = pd.concat([player_logs, pd.DataFrame([
        {"GAME_ID": "same-day", "TEAM_ABBREVIATION": "BOS", "PDK": 200, "GAME_DATE": "2026-10-25"},
        {"GAME_ID": "same-day", "TEAM_ABBREVIATION": "NYK", "PDK": 10, "GAME_DATE": "2026-10-25"},
    ])], ignore_index=True)
    inputs[1], inputs[2] = team_logs, player_logs

    result = _run(tuple(inputs))

    assert result["team_current_season_paired_games"].eq(20).all()
    assert result["team_current_season_pair_coverage"].eq(1.0).all()


@pytest.mark.parametrize("prior", [0, -1, float("nan"), float("inf")])
def test_invalid_shrinkage_prior_is_rejected(prior):
    inputs = _inputs()
    with pytest.raises(ValueError, match="shrinkage_prior_games"):
        compare_coach_roster_variants(
            inputs[0], team_logs=inputs[1], upcoming_schedule=inputs[3],
            player_logs=inputs[2], player_forecasts=inputs[4], season_id="26",
            gameweek=3, forecast_timestamp_utc="2026-10-25T09:00:00Z",
            current_season_start_utc="2026-10-01T00:00:00Z",
            shrinkage_prior_games=prior,
        )


def test_unparseable_or_missing_game_dates_fail_closed():
    inputs = list(_inputs())
    inputs[1]["GAME_DATE"] = inputs[1]["GAME_DATE"].astype(object)
    inputs[1].loc[0, "GAME_DATE"] = "not-a-date"
    with pytest.warns(UserWarning):
        with pytest.raises(ValueError, match="unparseable game dates"):
            _run(tuple(inputs))

    inputs = list(_inputs())
    inputs[2] = inputs[2].drop(columns="GAME_DATE")
    with pytest.raises(ValueError, match="game-date column"):
        _run(tuple(inputs))
