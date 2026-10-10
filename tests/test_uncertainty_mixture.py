import pandas as pd
import pytest

from dunkest.uncertainty.quantiles import (
    add_uncertainty_columns,
    interval_coverage_by_cohort,
)


def _forecast_row(play_probability: float, playing_mean: float = 40.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "expected_pdk": [play_probability * playing_mean],
            "expected_pdk_before_play_probability": [playing_mean],
            "p_play": [play_probability],
            "pdk_std_5": [20.0],
        }
    )


def _quantiles(play_probability: float) -> pd.DataFrame:
    return add_uncertainty_columns(
        _forecast_row(play_probability),
        residual_std=10.0,
        residual_q10=-10.0,
        residual_q50=0.0,
        residual_q90=10.0,
    )


def test_certain_availability_preserves_calibrated_playing_quantiles():
    result = _quantiles(1.0).iloc[0]

    assert result["p10"] == pytest.approx(20.0)
    assert result["p50"] == pytest.approx(40.0)
    assert result["p90"] == pytest.approx(60.0)


def test_questionable_player_quantiles_include_zero_if_absent_mass():
    result = _quantiles(0.5).iloc[0]

    assert result["p10"] == pytest.approx(0.0)
    assert result["p50"] == pytest.approx(0.0)
    assert result["p90"] == pytest.approx(53.1, abs=0.2)
    assert result["p10"] <= result["p50"] <= result["p90"]


def test_zero_play_probability_has_zero_score_quantiles():
    result = _quantiles(0.0).iloc[0]

    assert result["expected_pdk"] == pytest.approx(0.0)
    assert result["p10"] == pytest.approx(0.0)
    assert result["p50"] == pytest.approx(0.0)
    assert result["p90"] == pytest.approx(0.0)


def test_missing_uncertainty_inputs_remain_finite_and_ordered():
    frame = pd.DataFrame(
        {
            "expected_pdk": [8.0],
            "p_play": [0.5],
            "pdk_std_5": [float("nan")],
        }
    )

    result = add_uncertainty_columns(frame, residual_std=0.0)

    assert result[["p10", "p50", "p90", "pred_std"]].notna().all().all()
    assert result.loc[0, "p10"] <= result.loc[0, "p50"] <= result.loc[0, "p90"]


def test_interval_coverage_reports_history_and_minutes_cohorts():
    actual = pd.Series([10.0, 12.0, 30.0, 32.0, 18.0, 38.0])
    intervals = pd.DataFrame({"p10": actual - 2.0, "p90": actual + 2.0})
    history_games = pd.Series([2, 4, 8, 15, 24, 30])
    observed_minutes = pd.Series([8, 11, 20, 26, 29, 35])

    result = interval_coverage_by_cohort(
        actual,
        intervals,
        history_games=history_games,
        observed_minutes=observed_minutes,
        minimum_group_size=2,
    )
    by_group = {(row["dimension"], row["cohort"]): row for row in result}

    assert by_group[("all", "all")]["n"] == 6
    assert by_group[("history_games", "0-4")]["n"] == 2
    assert by_group[("history_games", "5-19")]["n"] == 2
    assert by_group[("history_games", "20+")]["n"] == 2
    assert by_group[("observed_minutes", "<12")]["p10_coverage"] == 1.0
    assert all(row["p90_coverage"] == 1.0 for row in result)
    assert by_group[("observed_minutes", "<12")]["meets_minimum_group_size"]
    assert not by_group[("observed_minutes", "12-23")]["meets_minimum_group_size"]
    assert not by_group[("observed_minutes", "32+")]["meets_minimum_group_size"]
