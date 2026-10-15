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



def test_training_target_mode_is_validated_and_normalized():
    assert Settings(training_target=" TARGET_PDK ").training_target == "target_pdk"
    assert Settings(training_target="auto").training_target == "auto"
    with pytest.raises(ValueError, match="training_target must be one of"):
        Settings(training_target="proxy-ish")


def test_season_opener_defaults_to_certified_multiseason_training():
    settings = Settings.from_yaml(Settings().root / "config" / "season_opener.yaml")
    assert settings.opening_multiseason_training is True
    assert settings.training_target == "target_pdk_official"
