import pytest

from dunkest.config import Settings


def test_unsupported_model_type_is_rejected():
    with pytest.raises(ValueError, match="only 'ensemble' is implemented"):
        Settings(model_type="ridge")


def test_unimplemented_betting_lines_setting_is_rejected():
    with pytest.raises(ValueError, match="use_betting_lines is not supported"):
        Settings(use_betting_lines=True)


def test_top_k_requires_distinct_rosters_and_caps_diversity_setting():
    with pytest.raises(ValueError, match="between 1 and 10"):
        Settings(min_different_players_top_k=0)

    assert Settings().min_different_players_top_k == 1


def test_market_cache_ttl_must_be_positive():
    with pytest.raises(ValueError, match="market_cache_max_age_hours must be positive"):
        Settings(market_cache_max_age_hours=0)
