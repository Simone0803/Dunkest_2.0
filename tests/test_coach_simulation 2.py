import numpy as np

from dunkest.models.coach import _simulate_matchup_scores


def test_coach_simulation_marks_overtime_only_for_one_point_resolved_games():
    team, opponent, overtime = _simulate_matchup_scores(
        112.0, 111.0, 12.0, 12.0, 0.1, "BOS-NYK-OT-test", 0.10, draws=20_000
    )

    assert np.all(team != opponent)
    assert np.all(np.abs(team[overtime] - opponent[overtime]) == 1)
    assert np.all(np.abs(team[~overtime] - opponent[~overtime]) >= 1)
    assert 0.09 <= float(overtime.mean()) <= 0.17


def test_coach_simulation_is_deterministic_and_ties_imply_overtime():
    first = _simulate_matchup_scores(
        112.0, 112.0, 12.0, 12.0, 0.1, "BOS-NYK-deterministic", 0.0, draws=5_000
    )
    second = _simulate_matchup_scores(
        112.0, 112.0, 12.0, 12.0, 0.1, "BOS-NYK-deterministic", 0.0, draws=5_000
    )

    for left, right in zip(first, second):
        assert np.array_equal(left, right)
    team, opponent, overtime = first
    assert overtime.any()
    assert np.all(np.abs(team[overtime] - opponent[overtime]) == 1)
    assert np.all(team != opponent)
