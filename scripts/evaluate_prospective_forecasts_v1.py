#!/usr/bin/env python3
"""Evaluate frozen, eligible pre-lock forecasts against official Dunkest outcomes.

This evaluator consumes the immutable pre-lock archive and the post-match bundle
written by ``build_dunkest_post_match_results_v1.py``. Partial observations are
reported as diagnostics and never labeled official OOS results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from archive_dunkest_pre_lock_run_v1 import digest, load_json  # noqa: E402
from review_dunkest_pre_lock_archive_v1 import review as review_prelock_archive  # noqa: E402
from dunkest.backtest.timing import safe_postgame_retrieval_cutoff  # noqa: E402


class UnverifiedOutcomeArchive(ValueError):
    """A readable outcome archive lacks the provenance needed for OOS labels."""


def _sha256_text(value: object) -> bool:
    token = str(value or "").strip().lower()
    return len(token) == 64 and all(char in "0123456789abcdef" for char in token)


def _nonempty_id(series: pd.Series) -> pd.Series:
    value = series.astype("string").str.strip()
    return value.notna() & value.ne("") & ~value.str.casefold().isin({"nan", "none", "<na>"})


def _truthy(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _metric_frame(frame: pd.DataFrame) -> dict | None:
    if frame.empty:
        return None
    error = pd.to_numeric(frame["predicted_pdk"], errors="coerce") - pd.to_numeric(
        frame["actual_pdk"], errors="coerce"
    )
    valid = np.isfinite(error.to_numpy(dtype=float))
    error = error.loc[valid]
    if error.empty:
        return None
    return {
        "n": int(len(error)),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt(np.square(error).mean())),
        "bias_predicted_minus_actual": float(error.mean()),
    }


def _group_metrics(frame: pd.DataFrame, key: str) -> dict:
    result = {}
    if frame.empty or key not in frame:
        return result
    for label, group in frame.groupby(key, dropna=False, sort=True):
        name = "unknown" if pd.isna(label) or not str(label).strip() else str(label)
        result[name] = _metric_frame(group)
    return result


def resolve_results_dir(data_dir: Path, season_id: str, gameweek: int, run_id: str) -> Path | None:
    root = data_dir / "archive" / str(season_id) / f"gw{int(gameweek)}"
    matches = []
    if not root.is_dir():
        return None
    for manifest_path in root.glob("post_match_*/manifest.json"):
        try:
            manifest = load_json(manifest_path)
            if str(manifest.get("run_id", "")) == str(run_id):
                matches.append((str(manifest.get("retrieved_at_utc", "")), manifest_path.parent))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return sorted(matches, key=lambda item: item[0])[-1][1] if matches else None


def validate_prelock_archive(archive_dir: Path) -> tuple[dict, dict, pd.DataFrame]:
    meta_path = archive_dir / "archive_manifest.json"
    if not meta_path.is_file():
        raise ValueError("Not an immutable pre-lock archive: archive_manifest.json is missing.")
    meta = load_json(meta_path)
    max_age = pd.to_numeric(pd.Series([meta.get("max_snapshot_age_hours")]), errors="coerce").iloc[0]
    if not np.isfinite(max_age) or max_age <= 0:
        raise ValueError("Pre-lock archive does not preserve a valid reviewer freshness window.")
    review = review_prelock_archive(archive_dir, float(max_age))
    if review.get("status") != "verified_pre_lock" or not review.get("rechecked_pre_lock_eligible"):
        raise ValueError(
            "Pre-lock reviewer did not certify this archive: "
            f"status={review.get('status')!r}, eligible={review.get('rechecked_pre_lock_eligible')!r}."
        )
    run_manifest = load_json(archive_dir / "manifest.json")
    descriptor = run_manifest.get("player_forecast_snapshot", {})
    forecast_path = archive_dir / Path(str(descriptor.get("path", "player_forecast_snapshot.parquet"))).name
    forecasts = pd.read_parquet(forecast_path)
    required = {
        "forecast_run_id", "forecast_record_id", "dunkest_player_id", "nba_game_id",
        "expected_pdk", "forecast_timestamp_utc", "prediction_cutoff_utc",
    }
    missing = sorted(required - set(forecasts.columns))
    if missing:
        raise ValueError(f"Eligible forecast snapshot lacks evaluator fields: {missing}")
    if forecasts.empty:
        raise ValueError("Eligible forecast snapshot contains no observations.")
    if not _nonempty_id(forecasts["forecast_record_id"]).all():
        raise ValueError("Forecast snapshot has missing forecast_record_id values.")
    if forecasts["forecast_record_id"].duplicated().any():
        raise ValueError("Forecast snapshot contains duplicate forecast_record_id values.")
    if not _nonempty_id(forecasts["dunkest_player_id"]).all() or not _nonempty_id(forecasts["nba_game_id"]).all():
        raise ValueError("Forecast snapshot has missing stable player or game identifiers.")
    identity = forecasts["dunkest_player_id"].astype("string") + "|" + forecasts["nba_game_id"].astype("string")
    if identity.duplicated().any():
        raise ValueError("Forecast snapshot contains duplicate stable player/game identities.")
    forecast_at = pd.to_datetime(forecasts["forecast_timestamp_utc"], utc=True, errors="coerce")
    cutoff = pd.to_datetime(forecasts["prediction_cutoff_utc"], utc=True, errors="coerce")
    if forecast_at.isna().any() or cutoff.isna().any() or (forecast_at >= cutoff).any():
        raise ValueError("Forecast timestamps are invalid or not strictly before their cutoffs.")
    run_id = str(run_manifest.get("run_id", ""))
    if not forecasts["forecast_run_id"].astype(str).eq(run_id).all():
        raise ValueError("Forecast record run IDs do not match the archived run.")
    return meta, run_manifest, forecasts


def _validate_results_archive(results_dir: Path, season_id: str, gameweek: int, run_id: str,
                              forecast_at: pd.Timestamp, fixtures: pd.DataFrame) -> tuple[dict, pd.DataFrame, dict]:
    manifest_path = results_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Post-match outcome manifest is missing.")
    manifest = load_json(manifest_path)
    try:
        schema = int(manifest.get("schema_version", 1))
    except (TypeError, ValueError):
        schema = 0
    if schema < 3:
        raise UnverifiedOutcomeArchive(
            "Outcome archive schema is not verifiable for stable forecast reconciliation (requires schema 3)."
        )
    if str(manifest.get("season_id")) != str(season_id) or int(manifest.get("dunkest_gameweek", -1)) != int(gameweek):
        raise ValueError("Outcome archive season/gameweek does not match the pre-lock bundle.")
    if str(manifest.get("run_id", "")) != str(run_id):
        raise ValueError("Outcome archive is not linked to the requested pre-lock run.")
    source_hashes = manifest.get("source_file_fingerprints", {})
    official_source = source_hashes.get("official_player_games", {})
    if not _sha256_text(official_source.get("sha256")) or not str(official_source.get("path", "")).strip():
        raise UnverifiedOutcomeArchive(
            "Outcome archive lacks a fingerprinted official Dunkest player-results source."
        )
    retrieved = pd.to_datetime(manifest.get("retrieved_at_utc"), utc=True, errors="coerce")
    if pd.isna(retrieved) or retrieved <= forecast_at:
        raise ValueError("Outcome acquisition timestamp is invalid or not after the forecast.")
    kickoffs = fixtures["game_datetime_utc"]
    safe_cutoff, _ = safe_postgame_retrieval_cutoff(kickoffs)
    if retrieved < safe_cutoff:
        raise ValueError("Outcome archive predates the conservative post-game retrieval cutoff.")
    registry_path = results_dir.parent / "registry" / f"{results_dir.name}.json"
    if not registry_path.is_file():
        raise ValueError("Immutable outcome registry record is missing.")
    registry = load_json(registry_path)
    if registry.get("archive_id") != results_dir.name or registry.get("manifest_sha256") != digest(manifest_path):
        raise ValueError("Outcome manifest does not match its immutable registry.")
    if (str(registry.get("season_id")) != str(season_id)
            or int(registry.get("dunkest_gameweek", -1)) != int(gameweek)
            or registry.get("sha256") != manifest.get("sha256")):
        raise ValueError("Outcome registry metadata differs from its manifest.")
    result_paths = {
        name: results_dir / name
        for name in ("player_results.parquet", "coach_results.parquet")
    }
    for name, path in result_paths.items():
        expected_hash = manifest.get("sha256", {}).get(name)
        if not path.is_file() or not _sha256_text(expected_hash) or expected_hash != digest(path) or registry.get("sha256", {}).get(name) != expected_hash:
            raise ValueError(f"Outcome archive file is missing or its registered hash differs: {name}")
    file_path = result_paths["player_results.parquet"]
    outcomes = pd.read_parquet(file_path)
    required = {
        "forecast_run_id", "forecast_record_id", "dunkest_player_id", "nba_game_id",
        "fixture_verified", "actual_pdk_official", "actual_pdk_status", "actual_pdk_source", "outcome_status",
    }
    missing = sorted(required - set(outcomes.columns))
    if missing:
        raise ValueError(f"Outcome table cannot be reconciled to versioned forecasts; missing: {missing}")
    provenance = {
        "outcome_manifest_sha256": digest(manifest_path),
        "outcome_registry_sha256": digest(registry_path),
        "official_player_results_sha256": digest(file_path),
        "official_source": official_source,
        "retrieved_at_utc": retrieved.isoformat(),
        "safe_postgame_cutoff_utc": safe_cutoff.isoformat(),
    }
    return manifest, outcomes, provenance


def reconcile_forecasts(forecasts: pd.DataFrame, outcomes: pd.DataFrame | None,
                        bundle_id: str, forecast_manifest: dict,
                        outcome_manifest: dict | None = None,
                        unavailable_status: str | None = None) -> pd.DataFrame:
    """One row per forecast; preserve excluded/missing/ambiguous outcomes explicitly."""
    rows = []
    duplicate_ids = set()
    duplicate_pairs = set()
    if outcomes is not None and not outcomes.empty:
        duplicate_ids = set(outcomes.loc[outcomes["forecast_record_id"].duplicated(keep=False), "forecast_record_id"].astype(str))
        outcome_pairs = outcomes["dunkest_player_id"].astype(str) + "|" + outcomes["nba_game_id"].astype(str)
        duplicate_pairs = set(outcome_pairs.loc[outcome_pairs.duplicated(keep=False)])
    outcome_by_id = {}
    if outcomes is not None:
        for _, outcome in outcomes.iterrows():
            forecast_id = str(outcome.get("forecast_record_id", ""))
            if forecast_id and forecast_id not in duplicate_ids:
                outcome_by_id[forecast_id] = outcome
    acquired_at = pd.to_datetime((outcome_manifest or {}).get("retrieved_at_utc"), utc=True, errors="coerce")
    for _, forecast in forecasts.iterrows():
        forecast_id = str(forecast["forecast_record_id"])
        player_id = str(forecast["dunkest_player_id"])
        game_id = str(forecast["nba_game_id"])
        reason = None
        outcome = None
        status = unavailable_status or ("outcome_archive_missing" if outcomes is None else "outcome_missing")
        if forecast_id in duplicate_ids:
            status, reason = "mapping_ambiguous", "duplicate_outcome_forecast_id"
        elif f"{player_id}|{game_id}" in duplicate_pairs:
            status, reason = "mapping_ambiguous", "duplicate_outcome_player_game_identity"
        elif outcomes is not None:
            outcome = outcome_by_id.get(forecast_id)
            if outcome is None:
                status, reason = "outcome_missing", "no_outcome_row_for_forecast_id"
            elif (str(outcome["forecast_run_id"]) != str(forecast["forecast_run_id"])
                  or str(outcome["dunkest_player_id"]) != player_id
                  or str(outcome["nba_game_id"]) != game_id):
                status, reason = "mapping_ambiguous", "forecast_player_or_game_reference_mismatch"
                outcome = None
            elif str(outcome.get("outcome_status", "")).strip().casefold() in {"postponed", "postponed_verified", "deferred"}:
                status, reason = "game_postponed", "official_fixture_marked_postponed"
                outcome = None
            elif not _truthy(outcome.get("fixture_verified")):
                status, reason = "mapping_ambiguous", "outcome_fixture_mapping_not_verified"
                outcome = None
            elif str(outcome.get("actual_pdk_status", "")) != "official_verified" or str(outcome.get("actual_pdk_source", "")) != "official_dunkest":
                source_status = str(outcome.get("actual_pdk_status", "missing"))
                if source_status == "ambiguous":
                    status = "mapping_ambiguous"
                    reason = "official_pdk_mapping_ambiguous"
                elif source_status == "missing":
                    status = "outcome_missing"
                    reason = "official_dunkest_pdk_missing"
                else:
                    status = "outcome_unverified"
                    reason = "outcome_source_is_not_official_dunkest"
                outcome = None
            else:
                observed = pd.to_numeric(pd.Series([outcome.get("actual_pdk_official")]), errors="coerce").iloc[0]
                if not np.isfinite(observed):
                    status, reason, outcome = "outcome_missing", "official_pdk_is_null_or_non_finite", None
                else:
                    status = "reconciled_official"
        predicted = pd.to_numeric(pd.Series([forecast.get("expected_pdk")]), errors="coerce").iloc[0]
        actual = (pd.to_numeric(pd.Series([outcome.get("actual_pdk_official")]), errors="coerce").iloc[0]
                  if outcome is not None else np.nan)
        if not np.isfinite(predicted):
            status, reason, actual = "forecast_invalid", "predicted_pdk_is_null_or_non_finite", np.nan
        rows.append({
            "forecast_record_id": forecast_id,
            "bundle_id": bundle_id,
            "forecast_run_id": str(forecast["forecast_run_id"]),
            "dunkest_player_id": player_id,
            "nba_game_id": game_id,
            "forecast_timestamp_utc": forecast.get("forecast_timestamp_utc"),
            "outcome_acquired_at_utc": acquired_at.isoformat() if pd.notna(acquired_at) else None,
            "predicted_pdk": float(predicted) if np.isfinite(predicted) else np.nan,
            "actual_pdk": float(actual) if np.isfinite(actual) else np.nan,
            "role": forecast.get("role"),
            "reconciliation_status": status,
            "exclusion_reason": reason,
            "actual_pdk_source": "official_dunkest" if status == "reconciled_official" else None,
            "outcome_status": outcome.get("outcome_status") if outcome is not None else None,
        })
    return pd.DataFrame(rows)


def build_report(archive_dir: Path, meta: dict, run_manifest: dict, forecasts: pd.DataFrame,
                 reconciled: pd.DataFrame, reviewer: dict, results_dir: Path | None,
                 outcome_provenance: dict | None) -> dict:
    evaluated = reconciled.loc[reconciled["reconciliation_status"].eq("reconciled_official")].copy()
    n_expected = len(forecasts)
    n_evaluated = len(evaluated)
    full_coverage = n_expected > 0 and n_evaluated == n_expected
    if full_coverage:
        status, metric_scope = "ready", "official_oos"
    elif n_evaluated:
        status, metric_scope = "partial", "verified_subset_diagnostic_only"
    else:
        status, metric_scope = "not_ready", "withheld_no_verified_observations"
    evaluated["observed_pdk_band"] = pd.cut(
        evaluated["actual_pdk"], [-np.inf, 10, 20, 25, 30, np.inf],
        labels=["<10", "10-<20", "20-<25", "25-<30", ">=30"], right=False,
    ) if not evaluated.empty else pd.Series(dtype="object")
    metrics = {
        "overall": _metric_frame(evaluated),
        "by_observed_pdk_band": _group_metrics(evaluated, "observed_pdk_band"),
        "by_role": _group_metrics(evaluated, "role"),
    } if n_evaluated else None
    counts = reconciled["reconciliation_status"].value_counts(dropna=False).to_dict()
    config = run_manifest.get("configuration", {})
    descriptor = run_manifest.get("player_forecast_snapshot", {})
    feature_rows = run_manifest.get("inputs", [])
    input_hashes = {str(row.get("path")): row.get("sha256") for row in feature_rows}
    run_id = str(run_manifest.get("run_id", archive_dir.name))
    registry_path = archive_dir.parents[2] / "registry" / f"{run_id}.json"
    report = {
        "evaluator_schema_version": 1,
        "evaluation_status": status,
        "metric_scope": metric_scope,
        "official_oos_metrics": bool(full_coverage and reviewer.get("rechecked_pre_lock_eligible")),
        "season_id": str(config.get("season_id", run_manifest.get("season_id", ""))),
        "gameweek": int(config.get("target_gameweek", run_manifest.get("target_gameweek", -1))),
        "run_id": run_id,
        "bundle_id": str(meta.get("run_id", archive_dir.name)),
        "archive_period": {
            "forecast_timestamp_utc": descriptor.get("forecast_timestamp_utc"),
            "cutoff_utc": descriptor.get("prediction_cutoff_utc"),
            "outcome_retrieved_at_utc": (outcome_provenance or {}).get("retrieved_at_utc"),
        },
        "model_version": descriptor.get("model_version"),
        "reviewer_status": reviewer.get("status"),
        "reviewer_pre_lock_eligible": bool(reviewer.get("rechecked_pre_lock_eligible")),
        "archive_manifest_sha256": digest(archive_dir / "archive_manifest.json"),
        "pre_lock_registry_sha256": digest(registry_path),
        "forecast_snapshot_sha256": digest(archive_dir / Path(str(descriptor.get("path", "player_forecast_snapshot.parquet"))).name),
        "bundle_file_hashes": {
            str(item.get("path")): item.get("sha256")
            for item in meta.get("files", [])
        },
        "pre_lock_input_hashes": input_hashes,
        "outcome_archive": str(results_dir) if results_dir else None,
        "outcome_provenance": outcome_provenance,
        "counts": {
            "forecasted": n_expected,
            "reconciled_official": n_evaluated,
            "excluded": n_expected - n_evaluated,
            "coverage": n_evaluated / n_expected if n_expected else 0.0,
            "by_status": {str(key): int(value) for key, value in sorted(counts.items(), key=lambda item: str(item[0]))},
        },
        "metrics": metrics,
        "exclusion_reasons": {str(key): int(value) for key, value in sorted(
            reconciled.loc[reconciled["exclusion_reason"].notna(), "exclusion_reason"].value_counts().items()
        )},
        "limitations": [],
    }
    if not full_coverage:
        report["limitations"].append(
            "Metrics on a verified subset are diagnostic only; official OOS metrics require every archived forecast row to reconcile to an official Dunkest PDK."
        )
    if results_dir is None:
        report["limitations"].append("No post-match official outcome archive linked to this run is available.")
    elif outcome_provenance and outcome_provenance.get("status") == "unverified":
        report["limitations"].append(str(outcome_provenance.get("reason")))
    if reconciled["reconciliation_status"].eq("outcome_missing").any():
        report["limitations"].append(
            "Absent official result rows remain missing; postponed fixtures cannot be identified unless the outcome source explicitly marks them as postponed."
        )
    return report


def evaluate_archive(archive_dir: Path, data_dir: Path | None = None,
                     results_dir: Path | None = None) -> tuple[dict, pd.DataFrame]:
    archive_dir = archive_dir.expanduser().resolve()
    meta, run_manifest, forecasts = validate_prelock_archive(archive_dir)
    config = run_manifest.get("configuration", {})
    season_id = str(config.get("season_id", run_manifest.get("season_id", "")))
    gameweek = int(config.get("target_gameweek", run_manifest.get("target_gameweek", -1)))
    run_id = str(run_manifest.get("run_id", archive_dir.name))
    reviewer = review_prelock_archive(archive_dir, float(meta["max_snapshot_age_hours"]))
    if results_dir is None and data_dir is not None:
        results_dir = resolve_results_dir(data_dir, season_id, gameweek, run_id)
    forecasts = forecasts.copy()
    forecasts["forecast_timestamp_utc"] = pd.to_datetime(forecasts["forecast_timestamp_utc"], utc=True, errors="coerce")
    latest_forecast = forecasts["forecast_timestamp_utc"].max()
    outcome_manifest, outcomes, provenance = None, None, None
    unavailable_status = None
    if results_dir is not None:
        fixture_candidates = [archive_dir / "pre_match_snapshot" / path.name
                              for path in archive_dir.glob("pre_match_snapshot/dunkest_fixture_mapping_*.parquet")]
        if len(fixture_candidates) != 1:
            raise ValueError(f"Expected one archived fixture mapping, found {len(fixture_candidates)}.")
        fixture_frame = pd.read_parquet(fixture_candidates[0])
        fixture_frame = fixture_frame.loc[
            pd.to_numeric(fixture_frame.get("dunkest_gameweek"), errors="coerce").eq(gameweek)
            & fixture_frame.get("mapping_verified", pd.Series(False, index=fixture_frame.index)).fillna(False).astype(bool)
        ].copy()
        if fixture_frame.empty:
            raise ValueError("No verified fixtures available for post-game timing validation.")
        fixture_ids = set(fixture_frame["nba_game_id"].astype(str))
        forecast_game_ids = set(forecasts["nba_game_id"].astype(str))
        if not forecast_game_ids.issubset(fixture_ids):
            raise ValueError("One or more forecast game IDs are absent from the verified frozen fixture mapping.")
        kickoffs = pd.to_datetime(fixture_frame["game_datetime_utc"], utc=True, errors="coerce")
        if kickoffs.isna().any():
            raise ValueError("Archived fixture mapping has invalid kickoff timestamps.")
        fixture_frame["game_datetime_utc"] = kickoffs
        try:
            outcome_manifest, outcomes, provenance = _validate_results_archive(
                results_dir.expanduser().resolve(), season_id, gameweek, run_id, latest_forecast, fixture_frame
            )
        except UnverifiedOutcomeArchive as exc:
            unavailable_status = "outcome_unverified"
            provenance = {"status": "unverified", "reason": str(exc)}
    reconciled = reconcile_forecasts(
        forecasts, outcomes, run_id, run_manifest, outcome_manifest, unavailable_status
    )
    report = build_report(archive_dir, meta, run_manifest, forecasts, reconciled, reviewer,
                          results_dir, provenance)
    return report, reconciled


def _write_idempotent(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"Refusing to overwrite a different evaluation artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True, help="Immutable pre-lock archive directory.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data", help="Root containing post-match outcome archives.")
    parser.add_argument("--results-dir", type=Path, help="Explicit verified post-match outcome archive.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/backtest/prospective_oos")
    args = parser.parse_args()
    try:
        report, rows = evaluate_archive(args.archive_dir, args.data_dir, args.results_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"prospective evaluation stopped: {exc}\n")
    run_id = report["run_id"]
    outcome_id = Path(report["outcome_archive"]).name if report["outcome_archive"] else "no_outcomes"
    stem = f"prospective_oos_{run_id}_{outcome_id}"
    json_payload = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    csv_payload = rows.to_csv(index=False, na_rep="").encode("utf-8")
    _write_idempotent(args.output_dir / f"{stem}.json", json_payload)
    _write_idempotent(args.output_dir / f"{stem}_observations.csv", csv_payload)
    print(json.dumps({
        "evaluation_status": report["evaluation_status"],
        "official_oos_metrics": report["official_oos_metrics"],
        "forecasted": report["counts"]["forecasted"],
        "reconciled_official": report["counts"]["reconciled_official"],
        "excluded": report["counts"]["excluded"],
        "metrics": report["metrics"],
        "outputs": [str(args.output_dir / f"{stem}.json"), str(args.output_dir / f"{stem}_observations.csv")],
    }, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if report["official_oos_metrics"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
