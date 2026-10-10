import pytest

from dunkest.optimize.milp import _portfolio_spread


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
