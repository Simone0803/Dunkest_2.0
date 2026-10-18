import pytest

from dunkest.optimize.milp import _grouped_portfolio_spread, _portfolio_spread


def test_portfolio_spread_is_root_sum_square_when_independent():
    assert _portfolio_spread([10.0, 10.0], correlation=0.0) == pytest.approx(2**0.5 * 10)


def test_portfolio_spread_uses_moderate_positive_correlation():
    spread = _portfolio_spread([10.0, 10.0], correlation=0.15)

    assert spread == pytest.approx(230**0.5)
    assert 2**0.5 * 10 < spread < 20.0


def test_single_player_spread_does_not_change_with_correlation():
    assert _portfolio_spread([7.5], correlation=0.15) == pytest.approx(7.5)


def test_empty_and_clamped_correlation_inputs_are_safe():
    assert _portfolio_spread([]) == 0.0
    assert _portfolio_spread([2.0, 3.0], correlation=-1.0) == pytest.approx(13**0.5)
    assert _portfolio_spread([2.0, 3.0], correlation=2.0) == pytest.approx(5.0)


def test_grouped_portfolio_spread_does_not_correlate_different_games():
    values = [10.0, 10.0, 10.0]
    groups = ["game-a", "game-b", "game-c"]
    assert _grouped_portfolio_spread(values, groups, correlation=0.15) == pytest.approx((300.0) ** 0.5)


def test_grouped_portfolio_spread_applies_correlation_only_within_same_game():
    values = [10.0, 10.0, 10.0]
    groups = ["game-a", "game-a", "game-b"]
    expected = (_portfolio_spread([10.0, 10.0], correlation=0.15) ** 2 + 10.0**2) ** 0.5
    assert _grouped_portfolio_spread(values, groups, correlation=0.15) == pytest.approx(expected)


def test_grouped_portfolio_spread_missing_fixture_ids_are_independent():
    assert _grouped_portfolio_spread([10.0, 10.0], [None, None], correlation=0.9) == pytest.approx((200.0) ** 0.5)


def test_grouped_portfolio_spread_requires_matching_group_count():
    with pytest.raises(ValueError, match="equal length"):
        _grouped_portfolio_spread([10.0], [])
