"""Reconcile frozen coach forecasts with authenticated post-match outcomes."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _number(value: Any) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) and np.isfinite(float(parsed)) else float("nan")


def _valid_id(value: Any) -> bool:
    return str(value).strip().casefold() not in {"", "nan", "none", "<na>"}


def _truthy(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().casefold() in {"true", "1", "yes"}


def reconcile_coach_forecasts(
    forecasts: pd.DataFrame,
    outcomes: pd.DataFrame | None,
    fixtures: pd.DataFrame,
    *,
    bundle_id: str,
    bundle_eligible: bool,
    forecast_manifest: dict,
    outcome_manifest: dict | None = None,
    outcome_verified: bool = True,
) -> pd.DataFrame:
    """Create one reconciliation row per coach forecast without guessing mappings."""
    required_forecast = {
        "forecast_record_id", "forecast_run_id", "nba_game_id", "team", "opponent",
        "forecast_timestamp_utc", "prediction_cutoff_utc", "expected_margin",
        "win_probability", "expected_coach_pdk",
    }
    required_fixtures = {
        "nba_game_id", "home_team", "away_team", "game_datetime_utc", "mapping_verified",
    }
    if missing := sorted(required_forecast - set(forecasts.columns)):
        raise ValueError(f"Coach forecasts lack required fields: {missing}")
    if missing := sorted(required_fixtures - set(fixtures.columns)):
        raise ValueError(f"Frozen fixtures lack required fields: {missing}")

    fixture_frame = fixtures.copy()
    fixture_frame["nba_game_id"] = fixture_frame["nba_game_id"].astype("string").str.strip()
    fixture_duplicates = set(
        fixture_frame.loc[fixture_frame["nba_game_id"].duplicated(keep=False), "nba_game_id"].astype(str)
    )
    fixture_by_id = {
        str(row["nba_game_id"]): row
        for _, row in fixture_frame.iterrows()
        if str(row["nba_game_id"]) not in fixture_duplicates
    }

    forecast_frame = forecasts.copy()
    forecast_frame["nba_game_id"] = forecast_frame["nba_game_id"].astype("string").str.strip()
    forecast_frame["team"] = forecast_frame["team"].astype("string").str.strip().str.upper()
    forecast_frame["opponent"] = forecast_frame["opponent"].astype("string").str.strip().str.upper()
    identity = forecast_frame["nba_game_id"].astype(str) + "|" + forecast_frame["team"].astype(str)
    duplicate_forecast_keys = set(identity[identity.duplicated(keep=False)])
    duplicate_forecast_ids = set(
        forecast_frame.loc[forecast_frame["forecast_record_id"].duplicated(keep=False), "forecast_record_id"].astype(str)
    )

    outcome_by_key: dict[tuple[str, str], pd.Series] = {}
    duplicate_outcome_keys: set[tuple[str, str]] = set()
    if outcomes is not None and not outcomes.empty:
        required_outcome = {"nba_game_id", "team", "opponent"}
        if missing := sorted(required_outcome - set(outcomes.columns)):
            raise ValueError(f"Coach outcomes lack identity fields: {missing}")
        normalized = outcomes.copy()
        normalized["nba_game_id"] = normalized["nba_game_id"].astype("string").str.strip()
        normalized["team"] = normalized["team"].astype("string").str.strip().str.upper()
        normalized["opponent"] = normalized["opponent"].astype("string").str.strip().str.upper()
        keys = list(zip(normalized["nba_game_id"].astype(str), normalized["team"].astype(str)))
        duplicate_outcome_keys = {
            key for key, duplicated in zip(keys, pd.Series(keys).duplicated(keep=False)) if duplicated
        }
        for key, (_, row) in zip(keys, normalized.iterrows()):
            if key not in duplicate_outcome_keys:
                outcome_by_key[key] = row

    forecast_at = pd.to_datetime(forecast_frame["forecast_timestamp_utc"], errors="coerce", utc=True)
    cutoff_at = pd.to_datetime(forecast_frame["prediction_cutoff_utc"], errors="coerce", utc=True)
    outcome_acquired = pd.to_datetime(
        (outcome_manifest or {}).get("retrieved_at_utc"), errors="coerce", utc=True
    )
    expected_run_id = str(forecast_manifest.get("run_id", ""))
    records: list[dict[str, Any]] = []

    for position, (_, forecast) in enumerate(forecast_frame.iterrows()):
        game_id = str(forecast.get("nba_game_id", "")).strip()
        team = str(forecast.get("team", "")).strip().upper()
        opponent = str(forecast.get("opponent", "")).strip().upper()
        record_id = str(forecast.get("forecast_record_id", "")).strip()
        key = (game_id, team)
        fixture = fixture_by_id.get(game_id)
        reason = ""
        status = "outcome_missing"
        outcome = None

        if not bundle_eligible:
            status, reason = "forecast_ineligible", "prelock_bundle_not_certified"
        elif not _valid_id(record_id) or not _valid_id(game_id) or not _valid_id(team):
            status, reason = "forecast_invalid", "stable_forecast_identity_missing"
        elif record_id in duplicate_forecast_ids or str(identity.iloc[position]) in duplicate_forecast_keys:
            status, reason = "mapping_ambiguous", "duplicate_forecast_game_team_identity"
        elif str(forecast.get("forecast_run_id", "")) != expected_run_id:
            status, reason = "forecast_invalid", "forecast_run_id_differs_from_manifest"
        elif pd.isna(forecast_at.iloc[position]) or pd.isna(cutoff_at.iloc[position]) or forecast_at.iloc[position] >= cutoff_at.iloc[position]:
            status, reason = "forecast_invalid", "forecast_timestamp_missing_or_not_before_cutoff"
        elif game_id in fixture_duplicates:
            status, reason = "mapping_ambiguous", "duplicate_fixture_game_id"
        elif fixture is None:
            status, reason = "mapping_ambiguous", "forecast_game_absent_from_frozen_fixture_mapping"
        elif not _truthy(fixture.get("mapping_verified", False)):
            status, reason = "mapping_ambiguous", "frozen_fixture_mapping_not_verified"
        else:
            kickoff = pd.to_datetime(fixture.get("game_datetime_utc"), errors="coerce", utc=True)
            home = str(fixture.get("home_team", "")).strip().upper()
            away = str(fixture.get("away_team", "")).strip().upper()
            if pd.isna(kickoff) or cutoff_at.iloc[position] >= kickoff:
                status, reason = "forecast_invalid", "cutoff_missing_or_not_before_game_start"
            elif {team, opponent} != {home, away} or team == opponent:
                status, reason = "mapping_ambiguous", "forecast_teams_do_not_match_frozen_fixture"
            elif not outcome_verified:
                status, reason = "outcome_unverified", "official_outcome_archive_failed_provenance_gate"
            elif outcomes is None:
                status, reason = "outcome_missing", "official_outcome_archive_missing"
            elif key in duplicate_outcome_keys:
                status, reason = "mapping_ambiguous", "duplicate_official_outcome_game_team_identity"
            else:
                outcome = outcome_by_key.get(key)
                if outcome is None:
                    status, reason = "outcome_missing", "no_official_outcome_for_game_team"
                elif str(outcome.get("opponent", "")).strip().upper() != opponent:
                    status, reason, outcome = "mapping_ambiguous", "outcome_opponent_differs_from_frozen_fixture", None
                elif pd.isna(outcome_acquired) or outcome_acquired <= forecast_at.iloc[position] or outcome_acquired < kickoff:
                    status, reason, outcome = "outcome_unverified", "outcome_acquisition_time_invalid", None
                else:
                    official_score = _number(outcome.get("actual_coach_pdk"))
                    team_points = _number(outcome.get("team_final_points"))
                    opponent_points = _number(outcome.get("opponent_final_points"))
                    if np.isfinite(official_score) or (np.isfinite(team_points) and np.isfinite(opponent_points)):
                        status, reason = "reconciled_official", ""
                    else:
                        status, reason, outcome = "outcome_missing", "official_coach_score_and_final_scores_missing", None

        if outcome is not None:
            actual_coach = _number(outcome.get("actual_coach_pdk"))
            team_points = _number(outcome.get("team_final_points"))
            opponent_points = _number(outcome.get("opponent_final_points"))
            actual_margin = team_points - opponent_points if np.isfinite(team_points) and np.isfinite(opponent_points) else float("nan")
            actual_win = float(team_points > opponent_points) if np.isfinite(actual_margin) else float("nan")
        else:
            actual_coach = actual_margin = actual_win = float("nan")

        records.append({
            "forecast_record_id": record_id, "bundle_id": bundle_id,
            "forecast_run_id": str(forecast.get("forecast_run_id", "")),
            "nba_game_id": game_id, "team": team, "opponent": opponent,
            "forecast_timestamp_utc": forecast.get("forecast_timestamp_utc"),
            "prediction_cutoff_utc": forecast.get("prediction_cutoff_utc"),
            "outcome_acquired_at_utc": outcome_acquired.isoformat() if pd.notna(outcome_acquired) else None,
            "expected_margin": _number(forecast.get("expected_margin")),
            "expected_margin_before_roster_adjustment": _number(forecast.get("expected_margin_before_roster_adjustment")),
            "win_probability": _number(forecast.get("win_probability")),
            "win_probability_before_roster_adjustment": _number(forecast.get("win_probability_before_roster_adjustment")),
            "expected_coach_pdk": _number(forecast.get("expected_coach_pdk")),
            "actual_margin": actual_margin, "actual_win": actual_win,
            "actual_coach_pdk": actual_coach,
            "team_roster_points_adjustment": _number(forecast.get("team_roster_points_adjustment")),
            "opponent_roster_points_adjustment": _number(forecast.get("opponent_roster_points_adjustment")),
            # Never infer PDK coverage from team_recent_games.
            "roster_adjustment_paired_pdk_games": _number(forecast.get("roster_adjustment_paired_pdk_games")),
            "roster_adjustment_fit_pair_count": _number(forecast.get("roster_adjustment_fit_pair_count")),
            "reconciliation_status": status, "exclusion_reason": reason or None,
        })
    return pd.DataFrame(records)


def _log_loss(probabilities: np.ndarray, labels: np.ndarray) -> tuple[float | str | None, int]:
    losses = []
    for probability, label in zip(probabilities, labels):
        if probability == 0.0:
            losses.append(0.0 if label == 0.0 else math.inf)
        elif probability == 1.0:
            losses.append(0.0 if label == 1.0 else math.inf)
        else:
            losses.append(-float(label * math.log(probability) + (1.0 - label) * math.log1p(-probability)))
    infinite = sum(math.isinf(value) for value in losses)
    if infinite:
        return "Infinity", infinite
    return (float(np.mean(losses)) if losses else None), 0


def _probability_metrics(frame: pd.DataFrame, probability_column: str) -> dict | None:
    values = frame[[probability_column, "actual_win"]].apply(pd.to_numeric, errors="coerce")
    values = values.loc[np.isfinite(values[probability_column]) & np.isfinite(values["actual_win"])]
    if values.empty or ((values[probability_column] < 0.0) | (values[probability_column] > 1.0)).any():
        return None
    probabilities = values[probability_column].to_numpy(dtype=float)
    labels = values["actual_win"].to_numpy(dtype=float)
    log_loss, infinite = _log_loss(probabilities, labels)
    return {
        "n_team_game_observations": int(len(values)),
        "n_games": int(frame.loc[values.index, "nba_game_id"].nunique()),
        "brier": float(np.mean(np.square(probabilities - labels))),
        "log_loss": log_loss,
        "log_loss_infinite_observations": int(infinite),
    }


def _error_metrics(frame: pd.DataFrame, predicted: str, actual: str) -> dict | None:
    values = frame[[predicted, actual]].apply(pd.to_numeric, errors="coerce")
    values = values.loc[np.isfinite(values[predicted]) & np.isfinite(values[actual])]
    if values.empty:
        return None
    error = values[predicted] - values[actual]
    return {
        "n_team_game_observations": int(len(values)),
        "n_games": int(frame.loc[values.index, "nba_game_id"].nunique()),
        "mae": float(error.abs().mean()), "rmse": float(np.sqrt(np.square(error).mean())),
        "bias_predicted_minus_actual": float(error.mean()),
    }


def _calibration(frame: pd.DataFrame) -> list[dict]:
    values = frame[["win_probability", "actual_win", "nba_game_id"]].copy()
    values["win_probability"] = pd.to_numeric(values["win_probability"], errors="coerce")
    values["actual_win"] = pd.to_numeric(values["actual_win"], errors="coerce")
    values = values.loc[
        np.isfinite(values["win_probability"]) & np.isfinite(values["actual_win"])
        & values["win_probability"].between(0.0, 1.0)
    ].copy()
    if values.empty:
        return []
    values["probability_bin"] = pd.cut(
        values["win_probability"], np.linspace(0.0, 1.0, 11), include_lowest=True
    )
    rows = []
    for interval, group in values.groupby("probability_bin", observed=False):
        if not group.empty:
            rows.append({
                "bin": str(interval), "n_team_game_observations": int(len(group)),
                "n_games": int(group["nba_game_id"].nunique()),
                "mean_predicted_probability": float(group["win_probability"].mean()),
                "observed_win_rate": float(group["actual_win"].mean()),
            })
    return rows


def evaluate_coach_rows(rows: pd.DataFrame) -> dict:
    """Summarize official rows; unverified or incomplete rows never enter metrics."""
    valid = rows.loc[rows["reconciliation_status"].eq("reconciled_official")].copy()
    status_counts = rows["reconciliation_status"].value_counts(dropna=False).to_dict() if not rows.empty else {}
    roster_coverage = None
    if "roster_adjustment_paired_pdk_games" in rows and rows["roster_adjustment_paired_pdk_games"].notna().any():
        observed = pd.to_numeric(rows["roster_adjustment_paired_pdk_games"], errors="coerce").dropna()
        roster_coverage = {
            "n_rows_with_measured_paired_pdk_games": int(len(observed)),
            "paired_pdk_games_min": float(observed.min()),
            "paired_pdk_games_median": float(observed.median()),
            "paired_pdk_games_max": float(observed.max()),
        }
    common_margin = valid.loc[
        np.isfinite(pd.to_numeric(valid["expected_margin"], errors="coerce"))
        & np.isfinite(pd.to_numeric(valid["expected_margin_before_roster_adjustment"], errors="coerce"))
        & np.isfinite(pd.to_numeric(valid["actual_margin"], errors="coerce"))
    ] if not valid.empty else valid
    common_probability = valid.loc[
        np.isfinite(pd.to_numeric(valid["win_probability"], errors="coerce"))
        & np.isfinite(pd.to_numeric(valid["win_probability_before_roster_adjustment"], errors="coerce"))
        & np.isfinite(pd.to_numeric(valid["actual_win"], errors="coerce"))
    ] if not valid.empty else valid
    return {
        "forecast_observations": int(len(rows)),
        "reconciled_observations": int(len(valid)),
        "reconciled_games": int(valid["nba_game_id"].nunique()) if not valid.empty else 0,
        "excluded_observations": int(len(rows) - len(valid)),
        "reconciliation_status_counts": {str(key): int(value) for key, value in status_counts.items()},
        "current_model": {
            "margin": _error_metrics(valid, "expected_margin", "actual_margin"),
            "win_probability": _probability_metrics(valid, "win_probability"),
            "coach_base_pdk": _error_metrics(valid, "expected_coach_pdk", "actual_coach_pdk"),
            "probability_calibration_bins": _calibration(valid),
        },
        "paired_current_model": {
            "margin": _error_metrics(common_margin, "expected_margin", "actual_margin"),
            "win_probability": _probability_metrics(common_probability, "win_probability"),
        },
        "without_roster_adjustment": {
            "margin": _error_metrics(common_margin, "expected_margin_before_roster_adjustment", "actual_margin"),
            "win_probability": _probability_metrics(common_probability, "win_probability_before_roster_adjustment"),
            "paired_margin_observations": int(len(common_margin)),
            "paired_probability_observations": int(len(common_probability)),
            "coach_base_pdk": None,
        },
        "roster_adjustment_coverage": roster_coverage or {
            "status": "unavailable",
            "reason": "snapshot lacks paired PDK counts; team_recent_games is not used as a substitute",
        },
        "shadow_variant_evaluation": {
            "status": "unavailable",
            "reason": "no certified shadow coach forecast snapshot is present",
        },
    }
