import math

import pandas as pd

from dunkest.backtest.realized_scoring import score_realized_team


def _players():
    slots = ["Captain", "Starter", "Starter", "Starter", "Starter", "Sixth Man", "Bench", "Bench", "Bench", "Bench"]
    return pd.DataFrame({"player_name": [f"Player {i}" for i in range(10)], "slot": slots})


def _scores():
    return {f"Player {i}": 10.0 for i in range(10)}


def test_realized_score_includes_coach_captain_sixth_and_transfer_malus():
    result = score_realized_team(
        _players(), _scores(), actual_coach_score=8.0,
        transfer_count=2, transfer_penalty=5.0, coach_fixture_verified=True,
    )
    assert result.complete
    assert result.player_score_before_transfers == 85.0
    assert result.coach_score == 8.0
    assert result.transfer_malus == 10.0
    assert result.team_score == 83.0


def test_realized_score_uses_dynamic_final_substitution_multipliers():
    players = _players()
    players["score_multiplier"] = [1.0, 0.5, 1.0, 1.0, 0.5, 1.0, 0.5, 0.5, 0.5, 0.5]
    result = score_realized_team(
        players, _scores(), actual_coach_score=0.0,
        transfer_count=0, transfer_penalty=5.0, coach_fixture_verified=True,
    )
    assert result.complete
    assert result.player_score_before_transfers == 7.0 * 10.0


def test_realized_score_rejects_invalid_explicit_score_multiplier():
    players = _players()
    players["score_multiplier"] = 1.0
    players.loc[0, "score_multiplier"] = -0.5
    result = score_realized_team(
        players, _scores(), actual_coach_score=0.0,
        transfer_count=0, transfer_penalty=5.0, coach_fixture_verified=True,
    )
    assert not result.complete
    assert result.reason == "invalid_player_score_multiplier"


def test_realized_score_rejects_missing_player_outcome_instead_of_partial_total():
    scores = _scores()
    scores.pop("Player 9")
    result = score_realized_team(
        _players(), scores, actual_coach_score=8.0,
        transfer_count=0, transfer_penalty=5.0, coach_fixture_verified=True,
    )
    assert not result.complete
    assert math.isnan(result.team_score)
    assert result.reason == "missing_player_actuals"


def test_realized_score_rejects_unverified_coach_or_unknown_transfer_count():
    no_coach = score_realized_team(
        _players(), _scores(), actual_coach_score=8.0,
        transfer_count=0, transfer_penalty=5.0, coach_fixture_verified=False,
    )
    assert not no_coach.complete
    assert no_coach.reason == "missing_or_unverified_coach_actual"
    no_transfers = score_realized_team(
        _players(), _scores(), actual_coach_score=8.0,
        transfer_count=float("nan"), transfer_penalty=5.0, coach_fixture_verified=True,
    )
    assert not no_transfers.complete
    assert no_transfers.reason == "invalid_transfer_count_or_penalty"
