"""Reproduce the paired evaluation of the archived 2026-27 GW1 forecast."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

from dunkest.evaluation.minutes_comparison import (
    minutes_metrics,
    paired_game_bootstrap_delta,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20261018T120440Z_88d2ef45"
RUN = ROOT / "data/archives/pre_lock/season_id=26/gw=1" / RUN_ID
OUTCOMES_PATH = ROOT / "data/processed/player_game_logs_2026-27.parquet"
AUDIT_DIR = ROOT / "reports/audit"
STEM = "dunkest_minutes_hybrid_shadow_paired_archive_20261024_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _name_key(value: object) -> str:
    ascii_name = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def _latest_metadata_timestamp(manifest: dict) -> str:
    stamps = []
    for item in manifest.get("inputs", []):
        value = (item.get("cache_metadata") or {}).get("fetched_at")
        if value:
            stamps.append(pd.Timestamp(value))
    if not stamps:
        raise ValueError("forecast manifest has no input acquisition timestamps")
    latest = max(stamps)
    if latest.tzinfo is None:
        raise ValueError("input acquisition timestamp lacks timezone")
    return latest.tz_convert("UTC").isoformat()


def _metric_row(frame: pd.DataFrame, label: str, prediction: str) -> dict:
    metrics = minutes_metrics(frame["minutes_actual"].to_numpy(), frame[prediction].to_numpy())
    return {
        "cohort": label,
        "n_records": metrics["n"],
        "n_players": int(frame["player_name"].nunique()),
        "n_games": int(frame["nba_game_id"].nunique()),
        "mae": metrics["mae"],
        "rmse": metrics["rmse"],
        "bias_pred_minus_actual": metrics["bias"],
    }


def build_evaluation() -> tuple[pd.DataFrame, dict]:
    manifest_path = RUN / "manifest.json"
    forecast_path = RUN / "predictions.parquet"
    manifest = json.loads(manifest_path.read_text())
    forecasts = pd.read_parquet(forecast_path)
    outcomes = pd.read_parquet(OUTCOMES_PATH)

    forecasts["player_name_key"] = forecasts["player_name"].map(_name_key)
    outcomes["player_name_key"] = outcomes["PLAYER_NAME"].map(_name_key)
    forecast_keys = ["player_name_key", "team", "nba_game_id"]
    outcome_keys = ["player_name_key", "TEAM_ABBREVIATION", "GAME_ID"]
    if forecasts.duplicated(forecast_keys).any() or outcomes.duplicated(outcome_keys).any():
        raise ValueError("ambiguous player-team-game mapping; refusing to score")

    forecast_at = pd.Timestamp(manifest["timestamp"])
    latest_metadata_at = pd.Timestamp(_latest_metadata_timestamp(manifest))
    if latest_metadata_at > forecast_at:
        raise ValueError("forecast archive contains an input acquired after forecast time")
    max_game_date = pd.to_datetime(outcomes["GAME_DATE"], utc=True).max()
    if forecast_at >= max_game_date + pd.Timedelta(days=1):
        raise ValueError("archived forecast is not earlier than observed target games")

    joined = forecasts.merge(
        outcomes,
        left_on=forecast_keys,
        right_on=outcome_keys,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_outcome"),
    )
    # An NBA game log row is evidence of positive participation only. Absence
    # from this endpoint is deliberately not converted to a zero-minute label.
    observed = joined.loc[joined["MIN"].notna()].copy()
    shadow_observed = observed.loc[observed["expected_min_model_shadow"].notna()].copy()
    if (observed["MIN"] < 0).any():
        raise ValueError("negative observed minutes")

    paired = shadow_observed.rename(
        columns={"MIN": "minutes_actual", "GAME_DATE": "game_date", "GAME_ID": "nba_game_id_outcome"}
    )
    paired["forecast_at_utc"] = forecast_at.isoformat()
    paired["latest_metadata_timestamp_utc"] = latest_metadata_at.isoformat()
    paired["feature_cutoff_utc"] = None
    paired["official_cutoff_utc"] = None
    paired["run_id"] = RUN_ID
    paired["run_git_hash"] = manifest.get("git_hash")
    paired["forecast_manifest_sha256"] = _sha256(manifest_path)
    paired["outcome_source"] = str(OUTCOMES_PATH.relative_to(ROOT))
    paired["outcome_source_sha256"] = _sha256(OUTCOMES_PATH)
    paired["identity_key_method"] = "normalized player name + team abbreviation + nba_game_id; unique exact key"
    paired["minutes_hybrid"] = paired["expected_min"]
    paired["minutes_hgb"] = paired["expected_min_model_shadow"]
    paired["minutes_actual"] = paired["minutes_actual"].astype(float)
    paired["game_date"] = pd.to_datetime(paired["game_date"], utc=True)
    paired["team_change_pre_cutoff"] = pd.NA
    paired["role_change_pre_cutoff"] = pd.NA
    # Forecast date is the information cut: all embedded source acquisition
    # timestamps are checked against it. Official Dunkest lock evidence is absent.
    paired = paired.sort_values(["game_date", "nba_game_id", "player_name"]).reset_index(drop=True)

    metric_rows = [
        _metric_row(paired, "paired_all_hybrid", "minutes_hybrid"),
        _metric_row(paired, "paired_all_hgb", "minutes_hgb"),
    ]
    by_date = []
    for date, group in paired.groupby(paired["game_date"].dt.date):
        by_date.append({
            "date": date.isoformat(),
            "hybrid": _metric_row(group, "date", "minutes_hybrid"),
            "hgb": _metric_row(group, "date", "minutes_hgb"),
        })
    for column, label in (("n_games", "history_lt5"), ("n_games", "history_ge5")):
        if column in paired:
            mask = paired[column].fillna(0) < 5 if label == "history_lt5" else paired[column].fillna(0) >= 5
            subset = paired.loc[mask]
            if len(subset):
                metric_rows.extend([
                    _metric_row(subset, f"{label}_hybrid", "minutes_hybrid"),
                    _metric_row(subset, f"{label}_hgb", "minutes_hgb"),
                ])

    subgroup_metrics = {}
    for column, field in (("role", "role"), ("lineup_group", "lineup_group")):
        groups = []
        for value, group in paired.groupby(column, dropna=False):
            name = "missing" if pd.isna(value) else str(value)
            groups.append({
                "group": name,
                "hybrid": _metric_row(group, name, "minutes_hybrid"),
                "hgb": _metric_row(group, name, "minutes_hgb"),
            })
        subgroup_metrics[field] = groups

    common = {
        "n_candidates": int(len(forecasts)),
        "n_candidates_with_hybrid": int(forecasts["expected_min"].notna().sum()),
        "n_candidates_with_hgb": int(forecasts["expected_min_model_shadow"].notna().sum()),
        "n_candidates_with_observed_log_row": int(len(observed)),
        "n_paired_scored": int(len(paired)),
        "n_paired_players": int(paired["player_name_key"].nunique()),
        "n_paired_games": int(paired["nba_game_id"].nunique()),
        "n_missing_log_outcome": int(len(forecasts) - len(observed)),
        "n_shadow_missing_among_observed": int(len(observed) - len(paired)),
        "n_zero_minutes_verified_from_logs": int((observed["MIN"] == 0).sum()),
        "n_absent_players_not_scored_as_zero": int(len(forecasts) - len(observed)),
    }
    diff_ci = paired_game_bootstrap_delta(paired)
    summary = {
        "run_id": RUN_ID,
        "season_id": manifest.get("configuration", {}).get("season_id"),
        "season": manifest.get("configuration", {}).get("season"),
        "gameweek": manifest.get("configuration", {}).get("target_gameweek"),
        "model_code_git_hash": manifest.get("git_hash"),
        "forecast_timestamp_utc": forecast_at.isoformat(),
        "latest_metadata_timestamp_utc": latest_metadata_at.isoformat(),
        "inputs_with_acquisition_timestamp": sum(
            bool((item.get("cache_metadata") or {}).get("fetched_at")) for item in manifest.get("inputs", [])
        ),
        "inputs_total": len(manifest.get("inputs", [])),
        "official_cutoff_utc": None,
        "manifest_pre_lock_eligible": bool(
            json.loads((RUN / "archive_manifest.json").read_text()).get("pre_lock_eligible", False)
        ),
        "forecast_source": str(forecast_path.relative_to(ROOT)),
        "forecast_manifest_sha256": _sha256(manifest_path),
        "outcome_source": str(OUTCOMES_PATH.relative_to(ROOT)),
        "outcome_source_sha256": _sha256(OUTCOMES_PATH),
        "target_game_dates": sorted(paired["game_date"].dt.strftime("%Y-%m-%d").unique().tolist()),
        "coverage": common,
        "metrics": metric_rows,
        "subgroup_metrics": subgroup_metrics,
        "observed_date_slices_not_independent_forecast_folds": by_date,
        "paired_delta_hgb_minus_hybrid_bootstrap_95_ci_by_nba_game": diff_ci,
        "bootstrap": {"method": "paired resampling of nba_game_id clusters", "replicates": 10000, "seed": 20261024},
        "limitations": [
            "One archived target GW only; this is not a multi-season walk-forward evaluation.",
            "Archive manifest marks pre_lock_eligible=false because fixture mapping freshness and Lineups snapshot validation failed.",
            "NBA logs contain rows only for observed player-game appearances here; absent candidates remain unlabelled, not zero minutes.",
            "Forecast output does not preserve canonical Dunkest player IDs; identity uses a unique normalized name/team/game key.",
            "No explicit official lock timestamp is present, so pre-lock certification is not claimed.",
            "Only 19 of 28 manifest input entries have fetched_at metadata; feature timing is not fully certified although all available acquisition timestamps precede the forecast.",
            "Team changes and role/rotation changes cannot be established against archived prior snapshots for this one target round.",
            "No faithful counterfactual PDK forecast can be reconstructed by substituting shadow minutes while holding the production predictor fixed.",
        ],
    }
    return paired, summary


def main() -> None:
    paired, summary = build_evaluation()
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    paired.to_csv(AUDIT_DIR / f"{STEM}_paired_records.csv", index=False)
    (AUDIT_DIR / f"{STEM}_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"coverage": summary["coverage"], "metrics": summary["metrics"], "delta_ci": summary["paired_delta_hgb_minus_hybrid_bootstrap_95_ci_by_nba_game"]}, indent=2))


if __name__ == "__main__":
    main()
