import numpy as np
import pandas as pd

from dunkest.evaluation.coach_prospective import (
    _log_loss,
    evaluate_coach_rows,
    reconcile_coach_forecasts,
)


def _inputs():
    forecasts = pd.DataFrame([
        {
            "forecast_record_id": "fc-home", "forecast_run_id": "run-1", "nba_game_id": "001",
            "team": "BOS", "opponent": "NYK", "forecast_timestamp_utc": "2026-10-20T12:00:00Z",
            "prediction_cutoff_utc": "2026-10-20T18:00:00Z", "expected_margin": 10,
            "expected_margin_before_roster_adjustment": 8, "win_probability": .75,
            "win_probability_before_roster_adjustment": .65, "expected_coach_pdk": 14,
            "team_roster_points_adjustment": 2, "roster_adjustment_paired_pdk_games": 4,
        },
        {
            "forecast_record_id": "fc-away", "forecast_run_id": "run-1", "nba_game_id": "001",
            "team": "NYK", "opponent": "BOS", "forecast_timestamp_utc": "2026-10-20T12:00:00Z",
            "prediction_cutoff_utc": "2026-10-20T18:00:00Z", "expected_margin": -10,
            "expected_margin_before_roster_adjustment": -8, "win_probability": .25,
            "win_probability_before_roster_adjustment": .35, "expected_coach_pdk": 14,
            "team_recent_games": 7,
        },
    ])
    fixtures = pd.DataFrame([{
        "nba_game_id": "001", "home_team": "BOS", "away_team": "NYK",
        "game_datetime_utc": "2026-10-20T19:00:00Z", "mapping_verified": True,
    }])
    outcomes = pd.DataFrame([
        {"nba_game_id": "001", "team": "BOS", "opponent": "NYK", "actual_coach_pdk": 15,
         "team_final_points": 110, "opponent_final_points": 100},
        {"nba_game_id": "001", "team": "NYK", "opponent": "BOS", "actual_coach_pdk": 12,
         "team_final_points": 100, "opponent_final_points": 110},
    ])
    return forecasts, outcomes, fixtures


def _reconcile(forecasts=None, outcomes=None, fixtures=None, *, eligible=True, acquired="2026-10-21T00:00:00Z"):
    base_forecasts, base_outcomes, base_fixtures = _inputs()
    return reconcile_coach_forecasts(
        forecasts if forecasts is not None else base_forecasts,
        outcomes if outcomes is not None else base_outcomes,
        fixtures if fixtures is not None else base_fixtures,
        bundle_id="bundle-1", bundle_eligible=eligible,
        forecast_manifest={"run_id": "run-1"}, outcome_manifest={"retrieved_at_utc": acquired},
    )


def test_reconciles_only_matching_frozen_game_and_teams():
    rows = _reconcile()
    assert rows["reconciliation_status"].tolist() == ["reconciled_official"] * 2
    assert rows["actual_margin"].tolist() == [10.0, -10.0]
    assert rows["actual_win"].tolist() == [1.0, 0.0]


def test_fixture_string_false_is_not_verified_and_wrong_team_mapping_is_excluded():
    _, _, fixtures = _inputs()
    fixtures["mapping_verified"] = "False"
    rows = _reconcile(fixtures=fixtures)
    assert set(rows["reconciliation_status"]) == {"mapping_ambiguous"}
    assert set(rows["exclusion_reason"]) == {"frozen_fixture_mapping_not_verified"}

    forecasts, _, _ = _inputs()
    forecasts.loc[0, "opponent"] = "PHI"
    rows = _reconcile(forecasts=forecasts)
    assert rows.loc[0, "reconciliation_status"] == "mapping_ambiguous"


def test_cutoff_duplicate_outcome_and_ineligible_bundle_are_excluded():
    forecasts, outcomes, fixtures = _inputs()
    forecasts.loc[0, "prediction_cutoff_utc"] = "2026-10-20T19:00:00Z"
    rows = _reconcile(forecasts=forecasts)
    assert rows.loc[0, "exclusion_reason"] == "cutoff_missing_or_not_before_game_start"

    outcomes = pd.concat([outcomes, outcomes.iloc[[0]]], ignore_index=True)
    rows = _reconcile(outcomes=outcomes)
    assert rows.loc[0, "exclusion_reason"] == "duplicate_official_outcome_game_team_identity"

    rows = _reconcile(eligible=False)
    assert set(rows["reconciliation_status"]) == {"forecast_ineligible"}


def test_missing_and_unverified_outcomes_are_explicit():
    rows = _reconcile(outcomes=pd.DataFrame(columns=["nba_game_id", "team", "opponent"]))
    assert set(rows["reconciliation_status"]) == {"outcome_missing"}
    rows = reconcile_coach_forecasts(
        _inputs()[0], _inputs()[1], _inputs()[2], bundle_id="bundle-1", bundle_eligible=True,
        forecast_manifest={"run_id": "run-1"}, outcome_verified=False,
    )
    assert set(rows["reconciliation_status"]) == {"outcome_unverified"}


def test_metrics_use_same_paired_rows_and_keep_coach_pdk_separate():
    rows = _reconcile()
    metrics = evaluate_coach_rows(rows)
    assert metrics["current_model"]["margin"] == {
        "n_team_game_observations": 2, "n_games": 1, "mae": 0.0, "rmse": 0.0,
        "bias_predicted_minus_actual": 0.0,
    }
    assert metrics["current_model"]["win_probability"]["brier"] == .0625
    assert np.isclose(metrics["current_model"]["win_probability"]["log_loss"], -np.log(.75))
    assert metrics["paired_current_model"]["margin"]["n_team_game_observations"] == 2
    assert metrics["without_roster_adjustment"]["margin"]["mae"] == 2.0
    assert metrics["without_roster_adjustment"]["paired_margin_observations"] == 2
    assert metrics["current_model"]["coach_base_pdk"]["mae"] == 1.5
    # team_recent_games must never be mistaken for paired PDK evidence.
    assert metrics["roster_adjustment_coverage"]["n_rows_with_measured_paired_pdk_games"] == 1


def test_log_loss_keeps_extreme_probability_failures_visible():
    assert _log_loss(np.array([0.0, 1.0]), np.array([0.0, 1.0])) == (0.0, 0)
    assert _log_loss(np.array([0.0, 1.0]), np.array([1.0, 0.0])) == ("Infinity", 2)
