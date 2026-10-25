from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import read_cache_metadata
from dunkest.data.dunkest.fixtures import check_backtest_readiness
from dunkest.optimize.milp import (
    LineupSolution,
    TEAM_PLAYER_SCORE_CORRELATION,
)


logger = logging.getLogger(__name__)
PLAYER_FORECAST_SCHEMA_VERSION = 1
RUNTIME_FEATURE_SCHEMA_VERSION = 1
SHADOW_FORECAST_SCHEMA_VERSION = 1
COACH_FORECAST_SCHEMA_VERSION = 1

PDK_REPLAY_REQUIRED_COLUMNS = {
    "forecast_run_id", "forecast_record_id", "dunkest_player_id", "canonical_player_id",
    "forecast_schema_version", "player_key", "nba_game_id", "dunkest_turn", "forecast_timestamp_utc",
    "prediction_cutoff_utc", "availability_observed_at_utc", "forecast_model_version",
    "forecast_configuration_sha256", "forecast_input_dataset_identifier",
    "forecast_source_fingerprint_sha256",
    "expected_min", "expected_min_model_shadow", "pdk_rate_for_projection", "p_play",
    "ensemble_pdk", "prior_pdk", "implied_min", "has_history", "n_games",
    "historical_rf_pdk", "historical_rf_blend_weight", "component_minutes_pdk",
    "component_ensemble_pdk", "component_prior_pdk", "projection_weight_minutes",
    "projection_weight_ensemble", "projection_weight_prior", "expected_pdk_conditional",
    "expected_pdk",
}


def _persist_versioned_snapshot(
    frame: pd.DataFrame,
    path: Path,
    artifact_name: str,
    persistence_errors: list[dict],
) -> str | None:
    """Write one new-run snapshot, returning its digest or recording failure."""
    try:
        frame.to_parquet(path, index=False)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        error = {
            "artifact": artifact_name,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        persistence_errors.append(error)
        logger.exception("Could not persist %s snapshot at %s", artifact_name, path)
        return None


def _git_hash() -> str | None:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return None


def _git_branch() -> str | None:
    try:
        value = subprocess.check_output(
            ["git", "branch", "--show-current"], stderr=subprocess.DEVNULL
        ).decode().strip()
        return value or None
    except Exception:
        return None


def _source_fingerprint(settings: Settings) -> dict:
    """Fingerprint production code and operational configuration, even without Git."""
    root = settings.root
    include_roots = (root / "src", root / "scripts", root / "config")
    extensions = {".py", ".sh", ".yaml", ".yml", ".toml", ".ini", ".json", ".csv"}
    files: set[Path] = set()
    for directory in include_roots:
        if directory.is_dir():
            files.update(
                path for path in directory.rglob("*")
                if path.is_file() and path.suffix.lower() in extensions
            )
    # Root-level launchers and package metadata affect the executable pipeline.
    for name in ("run-season-opener.sh", "run-backtest.sh", "pyproject.toml", "requirements.txt"):
        path = root / name
        if path.is_file():
            files.add(path)

    ordered_files = sorted(files, key=lambda path: path.relative_to(root).as_posix())
    digest = hashlib.sha256()
    counts = {"python_files": 0, "shell_files": 0, "config_files": 0}
    for path in ordered_files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
        if path.suffix.lower() == ".py":
            counts["python_files"] += 1
        elif path.suffix.lower() == ".sh":
            counts["shell_files"] += 1
        else:
            counts["config_files"] += 1
    return {
        "sha256": digest.hexdigest(),
        "files": len(ordered_files),
        **counts,
        "included_roots": ["src", "scripts", "config", "root_launchers"],
    }


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@contextmanager
def _atomic_new_directory(final_dir: Path):
    """Build an immutable archive privately, then publish it with one rename."""
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = final_dir.parent / f".{final_dir.name}.tmp-{uuid4().hex}"
    staging_dir.mkdir(parents=False, exist_ok=False)
    try:
        yield staging_dir
        if final_dir.exists():
            raise FileExistsError(f"Refusing to replace existing archive: {final_dir}")
        os.replace(staging_dir, final_dir)
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _input_paths(settings: Settings) -> list[Path]:
    processed = settings.data_path / "processed"
    log_season = settings.feature_season if settings.target_gameweek == 1 else settings.season
    paths = [
        processed / f"player_game_logs_{log_season}.parquet",
        processed / f"player_game_logs_{log_season}_official_pdk_overlay_v4.parquet",
        processed / f"player_game_logs_{log_season}_official_pdk_overlay.parquet",
        processed / f"team_game_logs_{log_season}.parquet",
        processed / f"schedule_{settings.season}.parquet",
        processed / f"future_regular_schedule_{settings.season}_v2.parquet",
        processed / f"dunkest_players_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        processed / f"player_credits_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        processed / f"coach_market_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        processed / f"injuries_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        processed / f"plusvalenza_history_{settings.opening_prior_season_id}.parquet",
        processed / f"dunkest_players_{settings.opening_prior_season_id}_gw35.parquet",
        processed / "dunkest_pdk_historical_random_forest_train_2020-25_test_2025-26_v1.joblib",
        processed / "dunkest_pdk_historical_random_forest_train_2020-25_test_2025-26_v1.json",
        processed / "dunkest_pdk_game_training_2020-26_v3.parquet",
        processed / "dunkest_nba_player_games_enriched_2018-25_v1.parquet",
        processed / "player_game_logs_2025-26.parquet",
        settings.data_path / "raw" / "nba_historical_logs_2018-25_v1" / "collection_manifest.json",
        settings.data_path / "current_lineups_market.csv",
        settings.data_path / "lineups_availability.csv",
        settings.data_path / "injury_overrides.csv",
        settings.data_path / "rookie_college.csv",
        settings.data_path / "rookie_official_pdk.csv",
        settings.root / "config" / "nba_coaches_2026.yaml",
        settings.root / "config" / "dunkest_coaches_2026-27.csv",
    ]
    # The multi-season PLUS loader may read a pre-GW anchor and per-season
    # caches whose season IDs are discovered from official Dunkest responses.
    # Fingerprint every versioned cache so the run remains reproducible even
    # when the selected historical seasons differ from the expected set.
    paths.extend(sorted(processed.glob("plusvalenza_history*_v4.parquet")))
    paths.extend(sorted(processed.glob(f"dunkest_fixture_mapping_{settings.season_id}_*.parquet")))
    return paths


def _input_fingerprints(settings: Settings) -> list[dict]:
    fingerprints = []
    for path in _input_paths(settings):
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        try:
            display_path = str(path.relative_to(settings.root))
        except ValueError:
            try:
                display_path = str(path.relative_to(settings.data_path))
            except ValueError:
                display_path = str(path)
        fingerprints.append({
            "path": display_path,
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
            "cache_metadata": read_cache_metadata(path),
        })
    return fingerprints


def _code_provenance(settings: Settings) -> dict:
    """Identify both the committed revision and the exact local source tree."""
    return {
        "git_hash": _git_hash(),
        "git_branch": _git_branch(),
        "source_fingerprint": _source_fingerprint(settings),
    }


def _package_versions() -> dict[str, str | None]:
    packages = (
        "numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "pulp",
        "nba_api", "xgboost", "lightgbm", "playwright",
    )
    versions = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def _runtime_feature_archive(
    candidates: pd.DataFrame,
    source_features: pd.DataFrame | None,
) -> pd.DataFrame:
    """Bind exact runtime feature rows to every frozen candidate without guessing."""
    identity_columns = [
        column for column in (
            "forecast_run_id", "forecast_record_id", "dunkest_player_id",
            "canonical_player_id", "player_key", "nba_game_id", "team",
            "opponent", "dunkest_turn", "forecast_timestamp_utc",
            "prediction_cutoff_utc", "expected_min", "expected_min_model_shadow",
            "minutes_hybrid_status", "minutes_shadow_status",
        ) if column in candidates.columns
    ]
    result = candidates[identity_columns].copy()
    if "player_key" not in result:
        result["player_key"] = pd.NA
    if "forecast_record_id" not in result:
        result["forecast_record_id"] = pd.Series(index=result.index, dtype="string")
    if result.empty:
        result["candidate_key_count"] = pd.Series(index=result.index, dtype="int64")
        result["source_feature_row_count"] = pd.Series(index=result.index, dtype="int64")
        result["feature_match_status"] = pd.Series(index=result.index, dtype="string")
        return result
    source = source_features.copy() if isinstance(source_features, pd.DataFrame) else pd.DataFrame()
    if not source.empty:
        if "player_key" not in source and "PLAYER_NAME" in source:
            from dunkest.names import player_key
            source["player_key"] = source["PLAYER_NAME"].map(player_key)
        if "player_key" not in source:
            source["player_key"] = pd.NA
        source["player_key"] = source["player_key"].astype("string").str.strip()
        source = source.loc[source["player_key"].notna() & source["player_key"].ne("")].copy()
    result["candidate_key_count"] = result.groupby("player_key", dropna=False)[
        "forecast_record_id"
    ].transform("size")
    if source.empty:
        result["source_feature_row_count"] = 0
        result["feature_match_status"] = "missing"
        return result
    source["source_feature_row_count"] = source.groupby("player_key")["player_key"].transform("size")
    source_counts = source.groupby("player_key")["source_feature_row_count"].max()
    source_unique = source.loc[source["source_feature_row_count"].eq(1)].copy()
    source_unique = source_unique.drop(columns="source_feature_row_count")
    rename = {
        column: f"runtime_feature__{column}"
        for column in source_unique.columns if column != "player_key"
    }
    source_unique = source_unique.rename(columns=rename)
    result = result.merge(source_unique, on="player_key", how="left", validate="many_to_one")
    result["source_feature_row_count"] = result["player_key"].map(source_counts).fillna(0).astype(int)
    result["feature_match_status"] = np.select(
        [result["candidate_key_count"].gt(1), result["source_feature_row_count"].gt(1),
         result["source_feature_row_count"].eq(1)],
        ["ambiguous_candidate_identity", "ambiguous_feature_identity", "matched"],
        default="missing",
    )
    return result


def _gameweek_fixture_snapshot(
    source: Path,
    *,
    season_id: str,
    gameweek: int,
    forecast_timestamp: pd.Timestamp,
) -> pd.DataFrame:
    """Return the verified target-GW slice of the active season mapping.

    Runtime consumers keep using the single season-wide mapping. A pre-lock
    bundle stores exactly one checked gameweek slice under the archive contract
    name; it is never a renamed copy of the whole season file.
    """
    from dunkest.data.dunkest.fixtures import validate_fixture_mapping

    source_mapping = validate_fixture_mapping(pd.read_parquet(source))
    season_rows = source_mapping.loc[
        source_mapping["season_id"].astype("string").eq(str(season_id))
    ].copy()
    target = season_rows.loc[
        pd.to_numeric(season_rows["dunkest_gameweek"], errors="coerce").eq(int(gameweek))
    ].copy()
    if target.empty:
        raise ValueError("active season mapping has no rows for the target gameweek")
    if not target["mapping_verified"].fillna(False).astype(bool).all():
        raise ValueError("target gameweek mapping contains unverified fixture rows")
    retrieved = pd.to_datetime(target["source_retrieved_at_utc"], errors="coerce", utc=True)
    if retrieved.isna().any() or (retrieved > forecast_timestamp).any():
        raise ValueError("target gameweek mapping has missing or post-forecast source timestamps")
    hashes = target["raw_payload_sha256"].fillna("").astype(str).str.strip().str.lower()
    if not hashes.map(lambda value: len(value) == 64 and all(c in "0123456789abcdef" for c in value)).all():
        raise ValueError("target gameweek mapping has missing or invalid source payload hashes")
    # The archive filename denotes the sliced bundle artifact. Preserve the
    # source mapping_version in each row as provenance of the active mapping.
    return target.reset_index(drop=True)


def save_run_artifacts(
    settings: Settings,
    predictions: pd.DataFrame,
    solutions: list[LineupSolution],
    models: dict | None = None,
    run_metadata: dict | None = None,
    *,
    coach_forecasts: pd.DataFrame | None = None,
) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    out_dir = settings.data_path / "predictions" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    persistence_errors: list[dict] = []
    input_fingerprints = _input_fingerprints(settings)
    configuration = asdict(settings)
    git_hash = _git_hash()
    source_fingerprint = _source_fingerprint(settings)
    config_sha256 = _json_hash(configuration)
    input_dataset_identifier = _json_hash(input_fingerprints)
    code_version = git_hash or source_fingerprint["sha256"]

    prediction_attrs = dict(predictions.attrs)
    # pandas serializes DataFrame.attrs into parquet metadata; the complete
    # candidate view is written as its own immutable table below.
    predictions.attrs = {
        key: value for key, value in prediction_attrs.items()
        if key not in {
            "candidate_forecasts", "dunkest_cutoff_evidence", "runtime_feature_snapshot",
            "dvp_snapshot",
        }
    }
    predictions.to_parquet(out_dir / "predictions.parquet", index=False)
    predictions.attrs = prediction_attrs
    # `predictions.parquet` is the optimizer-eligible view. Keep the complete
    # forecast candidate universe beside it so post-match reconciliation can
    # account for hard-outs and candidates with unresolved fixtures as well.
    candidate_forecasts = prediction_attrs.get("candidate_forecasts")
    if not isinstance(candidate_forecasts, pd.DataFrame):
        candidate_forecasts = predictions.copy()
    candidate_forecasts = candidate_forecasts.copy()
    candidate_forecasts.attrs = {}
    candidate_forecasts["forecast_run_id"] = run_id
    if "player_name" in candidate_forecasts:
        from dunkest.names import player_key

        candidate_forecasts["player_key"] = candidate_forecasts["player_name"].map(player_key)
        id_column = next(
            (column for column in ("dunkest_player_id", "player_id", "nba_player_id")
             if column in candidate_forecasts),
            None,
        )
        if id_column:
            supplied_id = candidate_forecasts[id_column].astype("string").str.strip()
            has_supplied_id = supplied_id.notna() & supplied_id.ne("")
            candidate_forecasts["canonical_player_id"] = supplied_id.where(
                has_supplied_id, candidate_forecasts["player_key"]
            )
            candidate_forecasts["canonical_player_id_source"] = id_column
            candidate_forecasts.loc[~has_supplied_id, "canonical_player_id_source"] = "normalized_player_key"
        else:
            candidate_forecasts["canonical_player_id"] = candidate_forecasts["player_key"]
            candidate_forecasts["canonical_player_id_source"] = "normalized_player_key"
    # Keep missing predictions explicit in the immutable all-candidate record.
    # A nullable numeric value alone does not distinguish an unavailable shadow
    # model from a prediction that was accidentally dropped upstream.
    for column in ("expected_min", "expected_min_model_shadow"):
        if column not in candidate_forecasts:
            candidate_forecasts[column] = pd.NA
    hybrid_available = pd.to_numeric(candidate_forecasts["expected_min"], errors="coerce").notna()
    shadow_available = pd.to_numeric(
        candidate_forecasts["expected_min_model_shadow"], errors="coerce"
    ).notna()
    candidate_forecasts["minutes_hybrid_status"] = hybrid_available.map(
        {True: "available", False: "unavailable"}
    )
    candidate_forecasts["minutes_shadow_status"] = shadow_available.map(
        {True: "available", False: "unavailable"}
    )
    candidate_forecasts["forecast_record_id"] = candidate_forecasts.apply(
        lambda row: hashlib.sha256(
            "|".join(str(row.get(key, "")) for key in (
                "forecast_run_id", "canonical_player_id", "nba_game_id", "dunkest_turn"
            )).encode("utf-8")
        ).hexdigest(),
        axis=1,
    )
    forecasted_at = pd.to_datetime(
        prediction_attrs.get("forecast_timestamp_utc", datetime.now(timezone.utc).isoformat()),
        errors="coerce", utc=True,
    )
    if pd.isna(forecasted_at):
        forecasted_at = pd.Timestamp.now(tz="UTC")
    candidate_forecasts["forecast_timestamp_utc"] = forecasted_at
    candidate_forecasts["fixture_kickoff_utc"] = pd.to_datetime(
        candidate_forecasts.get(
            "game_datetime_utc", pd.Series(pd.NaT, index=candidate_forecasts.index)
        ), errors="coerce", utc=True,
    )
    lock_metadata = dict(run_metadata or {})
    lock_timestamp_value = prediction_attrs.get("dunkest_lock_utc", lock_metadata.get("dunkest_lock_utc"))
    explicit_lock = pd.to_datetime(lock_timestamp_value, errors="coerce", utc=True)
    lock_source = str(
        prediction_attrs.get("dunkest_lock_source", lock_metadata.get("dunkest_lock_source", ""))
    ).strip()
    lock_source_sha256 = str(
        prediction_attrs.get("dunkest_lock_source_sha256", lock_metadata.get("dunkest_lock_source_sha256", ""))
    ).strip().lower()
    lock_verified = bool(
        prediction_attrs.get("dunkest_lock_verified", lock_metadata.get("dunkest_lock_verified", False))
        and len(lock_source_sha256) == 64
        and all(character in "0123456789abcdef" for character in lock_source_sha256)
        and pd.notna(explicit_lock)
    )
    candidate_forecasts["prediction_cutoff_utc"] = explicit_lock
    candidate_forecasts["availability_observed_at_utc"] = pd.to_datetime(
        candidate_forecasts.get(
            "availability_observed_at_utc", pd.Series(pd.NaT, index=candidate_forecasts.index)
        ), errors="coerce", utc=True,
    )
    candidate_forecasts["forecast_model_version"] = (
        code_version
    )
    candidate_forecasts["forecast_schema_version"] = PLAYER_FORECAST_SCHEMA_VERSION
    candidate_forecasts["forecast_configuration_sha256"] = config_sha256
    candidate_forecasts["forecast_input_dataset_identifier"] = input_dataset_identifier
    candidate_forecasts["forecast_code_version"] = code_version
    candidate_forecasts["forecast_source_fingerprint_sha256"] = source_fingerprint["sha256"]
    missing_pdk_replay_columns = sorted(
        PDK_REPLAY_REQUIRED_COLUMNS.difference(candidate_forecasts.columns)
    )
    for column in missing_pdk_replay_columns:
        candidate_forecasts[column] = pd.NA
    candidate_forecast_path = out_dir / "player_forecast_snapshot.parquet"
    candidate_forecast_sha256 = _persist_versioned_snapshot(
        candidate_forecasts, candidate_forecast_path, "player_forecast", persistence_errors
    )
    candidate_record_ids_unique = bool(
        "forecast_record_id" in candidate_forecasts
        and candidate_forecasts["forecast_record_id"].notna().all()
        and candidate_forecasts["forecast_record_id"].is_unique
    )
    runtime_feature_snapshot = _runtime_feature_archive(
        candidate_forecasts,
        prediction_attrs.get("runtime_feature_snapshot"),
    )
    runtime_feature_snapshot["runtime_feature_schema_version"] = RUNTIME_FEATURE_SCHEMA_VERSION
    runtime_feature_path = out_dir / "runtime_feature_snapshot.parquet"
    runtime_feature_sha256 = _persist_versioned_snapshot(
        runtime_feature_snapshot, runtime_feature_path, "runtime_feature", persistence_errors
    )

    shadow_columns = [
        "forecast_run_id", "forecast_record_id", "canonical_player_id", "dunkest_player_id",
        "player_key", "nba_game_id", "dunkest_turn", "forecast_timestamp_utc",
        "prediction_cutoff_utc", "forecast_model_version", "forecast_code_version",
        "forecast_configuration_sha256", "forecast_input_dataset_identifier",
        "forecast_source_fingerprint_sha256",
        "expected_min_model_shadow", "minutes_shadow_status",
    ]
    shadow_forecast_snapshot = candidate_forecasts.reindex(columns=[
        *[column for column in shadow_columns if column != "minutes_shadow_status"],
    ]).copy()
    shadow_available = pd.to_numeric(
        shadow_forecast_snapshot.get(
            "expected_min_model_shadow", pd.Series(index=shadow_forecast_snapshot.index, dtype=float)
        ), errors="coerce",
    ).notna()
    shadow_forecast_snapshot["minutes_shadow_status"] = shadow_available.map(
        {True: "available", False: "unavailable"}
    )
    shadow_forecast_snapshot["shadow_forecast_schema_version"] = SHADOW_FORECAST_SCHEMA_VERSION
    shadow_forecast_path = out_dir / "shadow_forecast_snapshot.parquet"
    shadow_forecast_sha256 = _persist_versioned_snapshot(
        shadow_forecast_snapshot, shadow_forecast_path, "shadow_forecast", persistence_errors
    )
    shadow_record_ids_unique = bool(
        shadow_forecast_snapshot.empty
        or (
            shadow_forecast_snapshot["forecast_record_id"].notna().all()
            and shadow_forecast_snapshot["forecast_record_id"].is_unique
        )
    )

    coach_snapshot_columns = [
        "forecast_run_id", "forecast_record_id", "coach_key", "coach", "team",
        "nba_game_id", "dunkest_turn", "forecast_timestamp_utc", "prediction_cutoff_utc",
        "expected_coach_pdk", "coach_cr", "forecast_model_version", "forecast_code_version",
        "forecast_configuration_sha256", "forecast_input_dataset_identifier",
        "forecast_source_fingerprint_sha256",
        "coach_forecast_schema_version",
    ]
    if isinstance(coach_forecasts, pd.DataFrame):
        coach_forecast_snapshot = coach_forecasts.copy()
        coach_forecast_snapshot.attrs = {}
    else:
        coach_forecast_snapshot = pd.DataFrame()
    if "coach" not in coach_forecast_snapshot:
        coach_forecast_snapshot["coach"] = pd.Series(index=coach_forecast_snapshot.index, dtype="string")
    if "team" not in coach_forecast_snapshot:
        coach_forecast_snapshot["team"] = pd.Series(index=coach_forecast_snapshot.index, dtype="string")
    if "nba_game_id" not in coach_forecast_snapshot:
        coach_forecast_snapshot["nba_game_id"] = pd.Series(index=coach_forecast_snapshot.index, dtype="string")
    if "dunkest_turn" not in coach_forecast_snapshot:
        coach_forecast_snapshot["dunkest_turn"] = pd.Series(index=coach_forecast_snapshot.index, dtype="Int64")
    missing_coach_columns = sorted({
        "coach", "team", "nba_game_id", "dunkest_turn", "expected_coach_pdk", "coach_cr",
    }.difference(coach_forecast_snapshot.columns))
    from dunkest.names import player_key
    coach_forecast_snapshot["forecast_run_id"] = run_id
    coach_forecast_snapshot["coach_key"] = coach_forecast_snapshot["coach"].map(player_key)
    coach_forecast_snapshot["forecast_record_id"] = coach_forecast_snapshot.apply(
        lambda row: hashlib.sha256("|".join(str(row.get(key, "")) for key in (
            "forecast_run_id", "coach_key", "team", "nba_game_id", "dunkest_turn"
        )).encode("utf-8")).hexdigest(), axis=1,
    )
    coach_forecast_snapshot["forecast_timestamp_utc"] = forecasted_at
    coach_forecast_snapshot["prediction_cutoff_utc"] = explicit_lock
    coach_forecast_snapshot["forecast_model_version"] = code_version
    coach_forecast_snapshot["forecast_code_version"] = code_version
    coach_forecast_snapshot["forecast_configuration_sha256"] = config_sha256
    coach_forecast_snapshot["forecast_input_dataset_identifier"] = input_dataset_identifier
    coach_forecast_snapshot["forecast_source_fingerprint_sha256"] = source_fingerprint["sha256"]
    coach_forecast_snapshot["coach_forecast_schema_version"] = COACH_FORECAST_SCHEMA_VERSION
    for column in coach_snapshot_columns:
        if column not in coach_forecast_snapshot:
            coach_forecast_snapshot[column] = pd.NA
    coach_forecast_path = out_dir / "coach_forecast_snapshot.parquet"
    coach_forecast_sha256 = _persist_versioned_snapshot(
        coach_forecast_snapshot, coach_forecast_path, "coach_forecast", persistence_errors
    )
    coach_record_ids_unique = bool(
        not coach_forecast_snapshot.empty
        and coach_forecast_snapshot["forecast_record_id"].notna().all()
        and coach_forecast_snapshot["forecast_record_id"].is_unique
    )
    coach_identity_ok = bool(
        coach_record_ids_unique
        and coach_forecast_snapshot["coach_key"].astype("string").notna().all()
        and coach_forecast_snapshot["coach_key"].astype("string").str.strip().ne("").all()
        and coach_forecast_snapshot["team"].astype("string").notna().all()
        and coach_forecast_snapshot["nba_game_id"].astype("string").notna().all()
        and coach_forecast_snapshot["nba_game_id"].astype("string").str.strip().ne("").all()
        and pd.to_numeric(
            coach_forecast_snapshot["dunkest_turn"], errors="coerce"
        ).notna().all()
    )

    archived_hgb_inputs = [
        column for column in runtime_feature_snapshot
        if str(column).startswith("runtime_feature__hgb_input__")
    ]
    archived_shadow_available = runtime_feature_snapshot.get(
        "minutes_shadow_status", pd.Series("unavailable", index=runtime_feature_snapshot.index)
    ).eq("available")
    hgb_values_finite = (
        bool(np.isfinite(runtime_feature_snapshot.loc[archived_shadow_available, archived_hgb_inputs]
                         .apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)).all())
        if archived_shadow_available.any() and archived_hgb_inputs else not archived_shadow_available.any()
    )
    runtime_feature_capture_ok = bool(
        len(runtime_feature_snapshot) == len(candidate_forecasts)
        and runtime_feature_snapshot["forecast_record_id"].is_unique
        and not runtime_feature_snapshot["feature_match_status"].isin(
            {"ambiguous_candidate_identity", "ambiguous_feature_identity"}
        ).any()
        and (
            not archived_shadow_available.any()
            or (
                archived_shadow_available.eq(
                    runtime_feature_snapshot["feature_match_status"].eq("matched")
                ).all()
                and bool(archived_hgb_inputs)
                and hgb_values_finite
            )
        )
    )
    cutoff_evidence = prediction_attrs.get("dunkest_cutoff_evidence")
    cutoff_evidence_path = None
    cutoff_evidence_sha256 = None
    if isinstance(cutoff_evidence, dict):
        cutoff_evidence_path = out_dir / "dunkest_cutoff_evidence.json"
        cutoff_evidence_path.write_text(
            json.dumps(cutoff_evidence, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        cutoff_evidence_sha256 = hashlib.sha256(cutoff_evidence_path.read_bytes()).hexdigest()
    lineup_rows = []
    for sol in solutions:
        coach_matchup = sol.meta.get("coach_matchup", {})
        turn_lineups = sol.meta.get("turn_lineups", {})
        for _, p in sol.players.iterrows():
            player_name = str(p["player_name"])
            turn_slots = {
                f"slot_turn_{turn}": lineup.get("slots", {}).get(player_name)
                for turn, lineup in turn_lineups.items()
            }
            turn_modules = {
                f"module_turn_{turn}": lineup.get("module")
                for turn, lineup in turn_lineups.items()
            }
            lineup_rows.append(
                {
                    "rank": sol.rank,
                    "player_name": p["player_name"],
                    "team": p.get("team"),
                    "opponent": p.get("opponent"),
                    "dunkest_turn": p.get("dunkest_turn"),
                    "nba_game_id": p.get("nba_game_id"),
                    "slot": p.get("slot"),
                    "score_multiplier": p.get("score_multiplier"),
                    **turn_slots,
                    **turn_modules,
                    "expected_team_pdk": sol.expected_team_pdk,
                    "expected_player_pdk": sol.expected_player_pdk,
                    "expected_coach_pdk": sol.expected_coach_pdk,
                    "player_expected_pdk_base": p.get("expected_pdk_base"),
                    "player_expected_pdk_dvp": p.get("expected_pdk"),
                    "player_dvp_adjustment_pdk_expected": p.get("dvp_adjustment_pdk_expected"),
                    "player_dvp_adjustment_fraction": p.get("dvp_adjustment_fraction"),
                    "player_dvp_signal_relative": p.get("dvp_signal_relative"),
                    "player_dvp_position": p.get("dvp_position"),
                    "player_dvp_values_used": p.get("dvp_values_used"),
                    "player_dvp_fallback_reason": p.get("dvp_fallback_reason"),
                    "raw_team_pdk": sol.raw_team_pdk,
                    "transfer_malus": sol.transfer_malus,
                    "p10_team": sol.p10_team,
                    "p50_team": sol.p50_team,
                    "p90_team": sol.p90_team,
                    "overlap_with_previous": sol.overlap_with_previous,
                    "overlap_with_prior_ranks": json.dumps(
                        sol.meta.get("overlap_with_prior_ranks", {}), sort_keys=True
                    ),
                    "budget_used": sol.budget_used,
                    "module": sol.module,
                    "num_transfers": sol.num_transfers,
                    "captain": sol.captain,
                    "captain_schedule": json.dumps(sol.meta.get("captain_schedule", {}), ensure_ascii=False, sort_keys=True),
                    "coach": sol.coach,
                    "coach_team": coach_matchup.get("coach_team"),
                    "coach_opponent": coach_matchup.get("coach_opponent"),
                    "coach_dunkest_turn": coach_matchup.get("coach_dunkest_turn"),
                    "coach_nba_game_id": coach_matchup.get("coach_nba_game_id"),
                    "coach_cr": coach_matchup.get("coach_cr"),
                    "opponent_coach": coach_matchup.get("opponent_coach"),
                    "opponent_coach_cr": coach_matchup.get("opponent_coach_cr"),
                    "coach_expected_pdk": coach_matchup.get("expected_coach_pdk", sol.expected_coach_pdk),
                    "coach_p10_pdk": coach_matchup.get("p10_coach_pdk"),
                    "coach_p50_pdk": coach_matchup.get("p50_coach_pdk"),
                    "coach_p90_pdk": coach_matchup.get("p90_coach_pdk"),
                    "coach_expected_team_pts": coach_matchup.get("expected_team_pts"),
                    "coach_expected_opp_pts": coach_matchup.get("expected_opp_pts"),
                    "coach_expected_margin": coach_matchup.get("expected_margin"),
                    "coach_win_probability": coach_matchup.get("win_probability"),
                    "coach_win_probability_before_roster_adjustment": coach_matchup.get("win_probability_before_roster_adjustment"),
                    "coach_projection_source": coach_matchup.get("coach_projection_source"),
                    "coach_matchup_available": coach_matchup.get("matchup_projection_available"),
                    "coach_opportunity_cost_pdk": coach_matchup.get("coach_opportunity_cost_pdk"),
                    "budget_shadow_price": sol.meta.get("budget_shadow_price"),
                    "capital_gain_shadow_price_method": sol.meta.get("capital_gain_shadow_price_method"),
                    "expected_budget_gain": sol.meta.get("expected_budget_gain"),
                    "future_budget_value_pdk": sol.meta.get("future_budget_value_pdk"),
                    "solver": sol.meta.get("solver", {}).get("solver"),
                    "solver_status": sol.meta.get("solver", {}).get("status"),
                    "solver_time_seconds": sol.meta.get("solver", {}).get("solve_time_seconds"),
                    "solver_objective_value": sol.meta.get("solver", {}).get("objective_value"),
                }
            )
    pd.DataFrame(lineup_rows).to_parquet(out_dir / "lineups.parquet", index=False)

    # Copy the pre-match decision inputs into the run directory. Hashes alone
    # identify a dataset but cannot replay it after a cache is replaced.
    snapshot_dir = out_dir / "pre_match_snapshot"
    snapshot_dir.mkdir()
    snapshot_files = []
    snapshot_names = {
        f"dunkest_players_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"player_credits_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"coach_market_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"injuries_{settings.season_id}_gw{settings.target_gameweek}.parquet",
    }
    processed_dir = settings.data_path / "processed"
    snapshot_paths = [processed_dir / name for name in snapshot_names]
    fixture_mapping_paths = sorted(
        processed_dir.glob(f"dunkest_fixture_mapping_{settings.season_id}_*.parquet")
    )
    dvp_descriptor = prediction_attrs.get("dvp_snapshot", {})
    dvp_selected = bool(dvp_descriptor.get("selected_pre_cutoff", False))
    dvp_source_path = Path(str(dvp_descriptor.get("path", ""))) if dvp_selected else None
    dvp_manifest_path = Path(str(dvp_descriptor.get("manifest_path", ""))) if dvp_selected else None
    if dvp_source_path is not None and dvp_source_path.is_file():
        snapshot_paths.append(dvp_source_path)
    if dvp_manifest_path is not None and dvp_manifest_path.is_file():
        snapshot_paths.append(dvp_manifest_path)
    snapshot_paths.extend(
        [
            settings.data_path / "current_lineups_market.csv",
            settings.data_path / "lineups_availability.csv",
            # Preserve the decision/provenance record explaining whether the
            # fixture mapping used a fresh observation or a verified fallback.
            settings.data_path / "lineups_fixtures_validation.json",
        ]
    )
    # Preserve acquisition metadata (especially fetched_at/source) alongside
    # the data bytes. The manifest hashes both files, so later audits can
    # distinguish "saved before tip-off" from a genuinely timestamped capture.
    snapshot_paths.extend(
        source_path.with_name(source_path.name + ".meta.json")
        for source_path in list(snapshot_paths)
        if source_path.with_name(source_path.name + ".meta.json").is_file()
    )
    dvp_copy_errors = []
    for source_path in sorted(snapshot_paths, key=str):
        if not source_path.is_file():
            continue
        destination_name = (
            "dunkest_dvp.parquet"
            if dvp_source_path is not None and source_path == dvp_source_path
            else "dunkest_dvp_manifest.json"
            if dvp_manifest_path is not None and source_path == dvp_manifest_path
            else source_path.name
        )
        destination = snapshot_dir / destination_name
        try:
            shutil.copy2(source_path, destination)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        except OSError as exc:
            if source_path in {dvp_source_path, dvp_manifest_path}:
                dvp_copy_errors.append(f"{source_path.name}:{type(exc).__name__}:{str(exc)[:250]}")
                continue
            raise
        snapshot_files.append({"path": destination.name, "sha256": digest, "source": str(source_path)})
    if dvp_descriptor:
        dvp_descriptor = dict(dvp_descriptor)
        bundled_dvp = next((entry for entry in snapshot_files if entry["path"] == "dunkest_dvp.parquet"), None)
        bundled_dvp_manifest = next((entry for entry in snapshot_files if entry["path"] == "dunkest_dvp_manifest.json"), None)
        if bundled_dvp is not None:
            # The run-local copy makes the optional source portable with the
            # archived forecast; it remains excluded from production features.
            dvp_descriptor["run_bundle_path"] = f"pre_match_snapshot/{bundled_dvp['path']}"
            dvp_descriptor["run_bundle_sha256"] = bundled_dvp["sha256"]
        if bundled_dvp_manifest is not None:
            dvp_descriptor["run_bundle_manifest_path"] = f"pre_match_snapshot/{bundled_dvp_manifest['path']}"
            dvp_descriptor["run_bundle_manifest_sha256"] = bundled_dvp_manifest["sha256"]
        if dvp_selected and (bundled_dvp is None or bundled_dvp_manifest is None or dvp_copy_errors):
            dvp_descriptor["persistence_status"] = "incomplete"
            dvp_descriptor["bundle_copy_errors"] = dvp_copy_errors or [
                "selected DvP source or source manifest is missing from the run bundle"
            ]
        elif dvp_selected:
            dvp_descriptor["persistence_status"] = "complete"

    # The active processed mapping must remain a single season-wide file for
    # existing runtime readers. Bundle only the verified target-GW rows under
    # the one filename required by the pre-lock archiver.
    expected_fixture_name = (
        f"dunkest_fixture_mapping_{settings.season_id}_lineups_browser_"
        f"gw{settings.target_gameweek}_team_status_v2.parquet"
    )
    if len(fixture_mapping_paths) == 1:
        try:
            fixture_snapshot = _gameweek_fixture_snapshot(
                fixture_mapping_paths[0],
                season_id=settings.season_id,
                gameweek=settings.target_gameweek,
                forecast_timestamp=forecasted_at,
            )
            fixture_destination = snapshot_dir / expected_fixture_name
            fixture_snapshot.to_parquet(fixture_destination, index=False)
            snapshot_files.append({
                "path": fixture_destination.name,
                "sha256": hashlib.sha256(fixture_destination.read_bytes()).hexdigest(),
                "source": str(fixture_mapping_paths[0]),
            })
        except Exception as exc:
            persistence_errors.append({
                "artifact": "fixture_mapping",
                "error_type": type(exc).__name__,
                "message": str(exc),
            })
            logger.exception("Could not create target-gameweek fixture mapping snapshot")
    elif fixture_mapping_paths:
        persistence_errors.append({
            "artifact": "fixture_mapping",
            "error_type": "ValueError",
            "message": (
                "expected exactly one active season mapping, found "
                f"{len(fixture_mapping_paths)}"
            ),
        })
        logger.error("Could not create target-gameweek fixture mapping snapshot: multiple active maps")

    dunkest_market_name = (
        f"dunkest_players_{settings.season_id}_gw{settings.target_gameweek}.parquet"
    )
    dunkest_market_snapshot = next(
        (item for item in snapshot_files if item["path"] == dunkest_market_name), None
    )
    dunkest_market_status = {
        "status": "present" if dunkest_market_snapshot else "missing",
        "path": dunkest_market_name,
        "sha256": dunkest_market_snapshot["sha256"] if dunkest_market_snapshot else None,
        "source": dunkest_market_snapshot["source"] if dunkest_market_snapshot else None,
        "reason": None if dunkest_market_snapshot else "required pre-lock Dunkest market snapshot was absent at archive time",
    }

    fitted_models = models or {}
    run_timestamp = datetime.now(timezone.utc)
    verified_candidates = (
        candidate_forecasts.get("fixture_verified", pd.Series(False, index=candidate_forecasts.index))
        .fillna(False).astype(bool)
    )
    stable_ids = candidate_forecasts.get(
        "dunkest_player_id", pd.Series(pd.NA, index=candidate_forecasts.index)
    ).astype("string").str.strip()
    candidate_game_ids = candidate_forecasts.get(
        "nba_game_id", pd.Series(pd.NA, index=candidate_forecasts.index)
    ).astype("string").str.strip()
    candidate_identity_ok = bool(
        not candidate_forecasts.empty
        and stable_ids.notna().all()
        and stable_ids.ne("").all()
        and candidate_game_ids.notna().all()
        and candidate_game_ids.ne("").all()
        and pd.to_numeric(
            candidate_forecasts.get(
                "dunkest_turn", pd.Series(pd.NA, index=candidate_forecasts.index)
            ), errors="coerce",
        ).notna().all()
        and candidate_forecasts.get(
            "canonical_player_id_source", pd.Series("", index=candidate_forecasts.index)
        ).eq("dunkest_player_id").all()
        and not (
            stable_ids + "|" + candidate_forecasts.get(
                "nba_game_id", pd.Series(pd.NA, index=candidate_forecasts.index)
            ).astype("string")
        ).duplicated().any()
    )
    evidence_cutoff_value = (
        cutoff_evidence.get("cutoff_utc") if isinstance(cutoff_evidence, dict) else None
    )
    evidence_acquired_values = (
        cutoff_evidence.get("acquired_at_utc", {}) if isinstance(cutoff_evidence, dict) else {}
    )
    evidence_acquired_times = pd.to_datetime(
        [evidence_acquired_values.get("config"), evidence_acquired_values.get("matchday")],
        errors="coerce", utc=True,
    )
    cutoff_evidence_temporal_ok = bool(
        isinstance(cutoff_evidence, dict)
        and cutoff_evidence.get("status") == "certified"
        and pd.notna(evidence_cutoff_value)
        and pd.to_datetime(evidence_cutoff_value, errors="coerce", utc=True)
        == pd.to_datetime(
            prediction_attrs.get("dunkest_lock_utc", lock_metadata.get("dunkest_lock_utc")),
            errors="coerce", utc=True,
        )
        and len(evidence_acquired_times) == 2
        and evidence_acquired_times.notna().all()
        and (evidence_acquired_times <= forecasted_at).all()
    )
    candidate_cutoffs = pd.to_datetime(
        candidate_forecasts.get("prediction_cutoff_utc", pd.Series(pd.NaT, index=candidate_forecasts.index)),
        errors="coerce", utc=True,
    )
    temporal_ok = bool(
        not candidate_forecasts.empty
        and candidate_identity_ok
        and runtime_feature_capture_ok
        and verified_candidates.all()
        and candidate_cutoffs.notna().all()
        and lock_verified and bool(lock_source)
        and isinstance(cutoff_evidence, dict)
        and cutoff_evidence.get("status") == "certified"
        and cutoff_evidence_temporal_ok
        and cutoff_evidence_sha256 is not None
        and cutoff_evidence.get("evidence_sha256") == lock_source_sha256
        and (forecasted_at < candidate_cutoffs).all()
        and run_timestamp < candidate_cutoffs.min()
    )
    input_times = []
    inputs_by_name = {Path(str(item.get("path", ""))).name: item for item in input_fingerprints}
    for item in input_fingerprints:
        metadata = item.get("cache_metadata") or {}
        timestamp = pd.to_datetime(metadata.get("fetched_at"), errors="coerce", utc=True)
        if pd.notna(timestamp):
            input_times.append(timestamp)
    dynamic_input_names = {
        "current_lineups_market.csv",
        f"dunkest_players_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"player_credits_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"coach_market_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"injuries_{settings.season_id}_gw{settings.target_gameweek}.parquet",
    }
    dynamic_input_timestamps_valid = True
    dynamic_input_times = {}
    for name in dynamic_input_names:
        item = inputs_by_name.get(name)
        metadata = (item or {}).get("cache_metadata") or {}
        timestamp = pd.to_datetime(metadata.get("fetched_at"), errors="coerce", utc=True)
        dynamic_input_times[name] = timestamp.isoformat() if pd.notna(timestamp) else None
        if item is None or pd.isna(timestamp) or timestamp > forecasted_at:
            dynamic_input_timestamps_valid = False
    inputs_temporal_ok = (
        all(timestamp <= forecasted_at for timestamp in input_times)
        and dynamic_input_timestamps_valid
    )
    fixture_mapping_ok = False
    fixture_path = next(
        (snapshot_dir / entry["path"] for entry in snapshot_files
         if entry["path"].startswith(f"dunkest_fixture_mapping_{settings.season_id}_")),
        None,
    )
    if fixture_path is not None and fixture_path.is_file():
        try:
            mapping_snapshot = pd.read_parquet(fixture_path)
            mapping_snapshot = mapping_snapshot.loc[
                pd.to_numeric(mapping_snapshot.get("dunkest_gameweek"), errors="coerce")
                .eq(int(settings.target_gameweek))
            ]
            fixture_mapping_ok = bool(
                not mapping_snapshot.empty
                and mapping_snapshot.get("mapping_verified", pd.Series(False, index=mapping_snapshot.index))
                .fillna(False).astype(bool).all()
                and pd.to_datetime(mapping_snapshot["source_retrieved_at_utc"], errors="coerce", utc=True).notna().all()
                and (pd.to_datetime(mapping_snapshot["source_retrieved_at_utc"], errors="coerce", utc=True) <= forecasted_at).all()
            )
        except Exception:
            fixture_mapping_ok = False
    player_snapshot_valid = bool(
        candidate_forecast_sha256 is not None
        and not candidate_forecasts.empty
        and not missing_pdk_replay_columns
        and candidate_record_ids_unique
        and candidate_identity_ok
    )
    runtime_snapshot_valid = bool(
        runtime_feature_sha256 is not None and runtime_feature_capture_ok
    )
    if shadow_forecast_sha256 is None or not shadow_record_ids_unique:
        shadow_snapshot_status = "incomplete"
    elif not shadow_available.any():
        shadow_snapshot_status = "unavailable"
    else:
        shadow_snapshot_status = "valid"
    coach_snapshot_valid = bool(
        coach_forecast_sha256 is not None
        and not coach_forecast_snapshot.empty
        and not missing_coach_columns
        and coach_identity_ok
    )
    snapshot_set_complete = bool(
        player_snapshot_valid and runtime_snapshot_valid and coach_snapshot_valid
        and shadow_snapshot_status != "incomplete"
        and dunkest_market_status["status"] == "present"
    )
    if not coach_forecast_snapshot.empty and missing_coach_columns:
        snapshot_set_complete = False
    archive_status = "complete" if snapshot_set_complete and not persistence_errors else "incomplete"

    manifest = {
        "schema_version": 2,
        "snapshot_schemas": {
            "player_forecast": PLAYER_FORECAST_SCHEMA_VERSION,
            "runtime_features": RUNTIME_FEATURE_SCHEMA_VERSION,
            "shadow_forecast": SHADOW_FORECAST_SCHEMA_VERSION,
            "coach_forecast": COACH_FORECAST_SCHEMA_VERSION,
        },
        "archive_status": archive_status,
        "snapshot_set_complete": snapshot_set_complete,
        "persistence_errors": persistence_errors,
        "prospective_evaluation_status": "awaiting_reconciled_outcomes",
        "run_id": run_id,
        "timestamp": run_timestamp.isoformat(),
        "git_hash": git_hash,
        "git_hash_unavailable_reason": (
            None if git_hash else "No resolvable commit is available; source_fingerprint identifies src/ instead."
        ),
        "git_branch": _git_branch(),
        "source_fingerprint": source_fingerprint,
        "configuration": configuration,
        "config_sha256": _json_hash(configuration),
        "random_seed": settings.random_state,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": _package_versions(),
        },
        "inputs": input_fingerprints,
        "pre_match_snapshot": {
            "path": str(snapshot_dir),
            "files": snapshot_files,
            "fixture_mapping_present": any(
                entry["path"].startswith("dunkest_fixture_mapping_") for entry in snapshot_files
            ),
        },
        # Optional diagnostic source. Its presence never changes bundle
        # eligibility and its timestamp/hash are verified by the DvP reader.
        "dvp_snapshot": dvp_descriptor or prediction_attrs.get(
            "dvp_snapshot", {"status": "unavailable", "reason": "not_captured"}
        ),
        "required_pre_match_inputs": {
            "dunkest_market_snapshot": dunkest_market_status,
        },
        "player_forecast_snapshot": {
            "schema_version": PLAYER_FORECAST_SCHEMA_VERSION,
            "status": "valid" if player_snapshot_valid else "incomplete",
            "path": candidate_forecast_path.name if candidate_forecast_sha256 else None,
            "sha256": candidate_forecast_sha256,
            "candidate_rows": int(len(candidate_forecasts)),
            "columns": [str(column) for column in candidate_forecasts.columns],
            "missing_pdk_replay_columns": missing_pdk_replay_columns,
            "forecast_record_ids_unique": candidate_record_ids_unique,
            "forecast_timestamp_utc": forecasted_at.isoformat(),
            "prediction_cutoff_utc": candidate_cutoffs.min().isoformat() if candidate_cutoffs.notna().any() else None,
            "cutoff_basis": lock_source or "missing_exact_dunkest_lock_timestamp",
            "cutoff_verified": lock_verified,
            "cutoff_source_sha256": lock_source_sha256 or None,
            "cutoff_status": (
                cutoff_evidence.get("status") if isinstance(cutoff_evidence, dict) else "uncertified"
            ),
            "certification_status": "certified" if (
                temporal_ok and fixture_mapping_ok and inputs_temporal_ok
            ) else "uncertified",
            "cutoff_kind": (
                cutoff_evidence.get("cutoff_kind") if isinstance(cutoff_evidence, dict) else "unknown"
            ),
            "cutoff_semantics": (
                cutoff_evidence.get("cutoff_semantics") if isinstance(cutoff_evidence, dict) else None
            ),
            "cutoff_evidence_path": (
                cutoff_evidence_path.name if cutoff_evidence_path is not None else None
            ),
            "cutoff_evidence_file_sha256": cutoff_evidence_sha256,
            "model_version": candidate_forecasts["forecast_model_version"].iloc[0] if not candidate_forecasts.empty else None,
            "input_dataset_identifier": _json_hash(input_fingerprints),
            "certification": {
                "pre_lock_eligible": bool(temporal_ok and fixture_mapping_ok and inputs_temporal_ok),
                "temporal_checks_passed": temporal_ok,
                "candidate_stable_identity_verified": candidate_identity_ok,
                "exact_dunkest_cutoff_verified": bool(lock_verified and lock_source),
                "cutoff_evidence_acquired_before_forecast": cutoff_evidence_temporal_ok,
                "timestamped_inputs_precede_forecast": bool(inputs_temporal_ok),
                "required_dynamic_input_timestamps_valid": bool(dynamic_input_timestamps_valid),
                "fixture_mapping_verified_before_forecast": fixture_mapping_ok,
                "reason": (
                    "verified candidate fixtures and forecast timestamp precede cutoff"
                    if temporal_ok and fixture_mapping_ok and inputs_temporal_ok
                    else "missing, unverified, untimed, or post-cutoff candidate/input evidence"
                ),
            },
        },
        "runtime_feature_snapshot": {
            "schema_version": RUNTIME_FEATURE_SCHEMA_VERSION,
            "status": "valid" if runtime_snapshot_valid else "incomplete",
            "path": runtime_feature_path.name if runtime_feature_sha256 else None,
            "sha256": runtime_feature_sha256,
            "candidate_rows": int(len(runtime_feature_snapshot)),
            "forecast_record_ids_unique": bool(
                runtime_feature_snapshot["forecast_record_id"].is_unique
            ),
            "feature_match_status_counts": {
                str(key): int(value)
                for key, value in runtime_feature_snapshot["feature_match_status"]
                .value_counts(dropna=False).items()
            },
            "runtime_feature_columns": [
                str(column) for column in runtime_feature_snapshot.columns
                if str(column).startswith("runtime_feature__")
            ],
            "hgb_input_columns": [
                str(column) for column in runtime_feature_snapshot.columns
                if str(column).startswith("runtime_feature__hgb_input__")
            ],
            "model_feature_columns": list(
                prediction_attrs.get("minutes_shadow_feature_columns", [])
            ),
            "source_input_dataset_identifier": _json_hash(input_fingerprints),
            "source_input_provenance": [
                {
                    "path": item["path"], "sha256": item["sha256"],
                    "fetched_at_utc": (item.get("cache_metadata") or {}).get("fetched_at"),
                    "source": (item.get("cache_metadata") or {}).get("source"),
                }
                for item in input_fingerprints
            ],
            "certification_status": "valid" if runtime_feature_capture_ok else "invalid",
        },
        "shadow_forecast_snapshot": {
            "schema_version": SHADOW_FORECAST_SCHEMA_VERSION,
            "status": shadow_snapshot_status,
            "path": shadow_forecast_path.name if shadow_forecast_sha256 else None,
            "sha256": shadow_forecast_sha256,
            "rows": int(len(shadow_forecast_snapshot)),
            "available_rows": int(shadow_available.sum()),
            "forecast_record_ids_unique": shadow_record_ids_unique,
            "optimizer_input": False,
        },
        "coach_forecast_snapshot": {
            "schema_version": COACH_FORECAST_SCHEMA_VERSION,
            "status": "valid" if coach_snapshot_valid else "incomplete",
            "path": coach_forecast_path.name if coach_forecast_sha256 else None,
            "sha256": coach_forecast_sha256,
            "rows": int(len(coach_forecast_snapshot)),
            "columns": [str(column) for column in coach_forecast_snapshot.columns],
            "missing_required_columns": missing_coach_columns,
            "forecast_record_ids_unique": coach_record_ids_unique,
            "stable_identity_verified": coach_identity_ok,
            "forecast_timestamp_utc": forecasted_at.isoformat(),
            "prediction_cutoff_utc": explicit_lock.isoformat() if pd.notna(explicit_lock) else None,
        },
        "dataset_identifier": _json_hash(input_fingerprints),
        "run_metadata": dict(run_metadata or {}),
        "degradations": sorted(set(
            (run_metadata or {}).get("degradations", predictions.attrs.get("forecast_degradations", []))
        )),
        "verification": {
            "fixture_mapping_present": any(
                entry["path"].startswith("dunkest_fixture_mapping_") for entry in snapshot_files
            ),
            "fixture_mapping_source_verified": bool(
                (run_metadata or {}).get("fixture_mapping_source_verified", False)
            ),
            "coach_matchups_verified": bool(
                (run_metadata or {}).get("coach_matchups_verified", all(
                    bool(solution.meta.get("coach_matchup", {}).get("matchup_projection_available", False))
                    for solution in solutions
                ) and bool(solutions))
            ),
            "injury_snapshot_verified": bool(
                (run_metadata or {}).get("injury_snapshot_verified", bool(
                    settings.use_injuries
                    and "injury_snapshot_missing_or_empty" not in predictions.attrs.get("forecast_degradations", [])
                ))
            ),
            "dunkest_market_snapshot_present": dunkest_market_status["status"] == "present",
        },
        "model_details": {
            "effective_models": sorted(
                key for key in fitted_models if not key.startswith("_")
            ),
            "feature_columns": fitted_models.get("_feature_cols", []),
            "minutes_shadow": {
                "available": fitted_models.get("_minutes_shadow_model") is not None,
                "class": (
                    type(fitted_models["_minutes_shadow_model"]).__name__
                    if fitted_models.get("_minutes_shadow_model") is not None else None
                ),
                "parameters": (
                    fitted_models["_minutes_shadow_model"].get_params(deep=False)
                    if fitted_models.get("_minutes_shadow_model") is not None else None
                ),
                "training_rows": fitted_models.get("_minutes_shadow_training_rows", 0),
                "target": fitted_models.get("_minutes_shadow_target", "target_min"),
            },
            "training_target": fitted_models.get("_training_target"),
            "training_target_source": fitted_models.get("_training_target_source"),
            "training_rows": fitted_models.get("_training_rows"),
            "training_rows_before_target_filter": fitted_models.get("_training_rows_before_target_filter"),
            "official_labels_available_before_filter": fitted_models.get("_official_labels_available_before_filter"),
            "training_date_min_utc": fitted_models.get("_training_date_min_utc"),
            "training_date_max_utc": fitted_models.get("_training_date_max_utc"),
            "training_seasons": fitted_models.get("_training_seasons", []),
            "training_dataset": fitted_models.get("_training_dataset"),
            "training_minute_labels_dataset": fitted_models.get("_training_minute_labels_dataset"),
            "training_minute_labels_matched_rows": fitted_models.get("_training_minute_labels_matched_rows"),
            "training_label_certification": fitted_models.get("_training_label_certification"),
            "sample_weighted_training": fitted_models.get("_sample_weighted_training", False),
            "sample_weight_mean": fitted_models.get("_sample_weight_mean"),
            "residual_std": fitted_models.get("_residual_std"),
            "residual_q10": fitted_models.get("_residual_q10"),
            "residual_q50": fitted_models.get("_residual_q50"),
            "residual_q90": fitted_models.get("_residual_q90"),
            "rookie_policy": fitted_models.get("_rookie_policy"),
            "prediction_is_absolute": fitted_models.get("_prediction_is_absolute", False),
            "model_weights": fitted_models.get("_weights", {}),
            "projection_weights": fitted_models.get("_projection_weights", {}),
            "calibration_samples": fitted_models.get("_calibration_samples"),
            "interval_diagnostics": fitted_models.get("_interval_diagnostics", []),
            "interval_diagnostic_scope": fitted_models.get("_interval_diagnostic_scope"),
        },
        "season": settings.season,
        "target_gameweek": settings.target_gameweek,
        "backtest_readiness": check_backtest_readiness(settings, settings.target_gameweek),
        "budget": settings.budget,
        "optimizer_objective": settings.optimizer_objective,
        "risk_lambda": settings.risk_lambda,
        "optimizer_parameters": {
            "objective": settings.optimizer_objective,
            "risk_lambda": settings.risk_lambda,
            "top_k": settings.optimizer_top_k,
            "risk_lambda_grid": settings.optimizer_risk_lambda_grid,
            "budget": settings.budget,
            "transfer_penalty": settings.transfer_penalty,
            "capital_gain_budget_delta": settings.capital_gain_budget_delta,
        },
        "team_player_score_correlation": TEAM_PLAYER_SCORE_CORRELATION,
        "model_type": settings.model_type,
        "feature_flags": {
            "use_matchup": settings.use_matchup,
            "use_injuries": settings.use_injuries,
            "use_schedule": settings.use_schedule,
            "use_coach_model": settings.use_coach_model,
        },
        "paths": {
            "predictions": str(out_dir / "predictions.parquet"),
            "lineups": str(out_dir / "lineups.parquet"),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_dir



def save_pre_match_snapshot(
    settings: Settings,
    gameweek: int,
    tables: dict[str, pd.DataFrame],
    *,
    source: str,
    metadata: dict | None = None,
) -> Path:
    """Persist immutable, hash-verified point-in-time inputs for a gameweek.

    Outcome-bearing fields are rejected so realized scores cannot accidentally
    enter a pre-match archive. The caller must pass sanitized market/context
    tables and explicitly state their provenance.
    """
    if not source.strip():
        raise ValueError("Pre-match snapshot source must be explicit.")
    if not tables:
        raise ValueError("Pre-match snapshot requires at least one input table.")
    forbidden = {
        "actual_pdk", "actual_coach_pdk", "target_pdk", "pdk_official_valid",
        "pdk_official_raw", "gameweek_stats_available", "realized_score",
    }
    normalized_tables: dict[str, pd.DataFrame] = {}
    for name, frame in tables.items():
        safe_name = str(name).strip()
        if not safe_name or Path(safe_name).name != safe_name or not safe_name.endswith(".parquet"):
            raise ValueError(f"Invalid pre-match table name: {name!r}")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"Pre-match input {safe_name} must be a DataFrame.")
        leaked = sorted(forbidden.intersection(str(column).strip().casefold() for column in frame.columns))
        if leaked:
            raise ValueError(f"Outcome-bearing column(s) forbidden in pre-match archive {safe_name}: {leaked}")
        normalized_tables[safe_name] = frame.copy()
    extra = dict(metadata or {})
    reserved = {
        "season_id", "dunkest_gameweek", "captured_at_utc", "source", "schema_version",
        "sha256", "git_hash", "git_branch", "source_fingerprint",
    }
    conflicts = sorted(reserved.intersection(extra))
    if conflicts:
        raise ValueError(f"Pre-match metadata cannot override reserved fields: {conflicts}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = settings.data_path / "archive" / str(settings.season_id) / f"gw{int(gameweek)}"
    out = root / f"pre_match_{stamp}_{uuid4().hex[:8]}"
    with _atomic_new_directory(out) as staging_dir:
        hashes: dict[str, str] = {}
        for name, frame in sorted(normalized_tables.items()):
            path = staging_dir / name
            frame.to_parquet(path, index=False)
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {
            "season_id": settings.season_id,
            "dunkest_gameweek": int(gameweek),
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "schema_version": 1,
            **_code_provenance(settings),
            "sha256": hashes,
            "table_rows": {name: int(len(frame)) for name, frame in normalized_tables.items()},
        }
        manifest.update(extra)
        (staging_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    return out

def save_post_match_snapshot(
    settings: Settings,
    gameweek: int,
    player_results: pd.DataFrame,
    coach_results: pd.DataFrame,
    *,
    source: str,
    metadata: dict | None = None,
) -> Path:
    """Archive realized outcomes immutably for future fixture-linked replay."""
    if not source.strip():
        raise ValueError("Post-match result source must be explicit.")
    extra_metadata = dict(metadata or {})
    reserved_fields = {
        "season_id", "dunkest_gameweek", "retrieved_at_utc", "source", "schema_version",
        "sha256", "git_hash", "git_branch", "source_fingerprint",
    }
    conflicts = sorted(reserved_fields.intersection(extra_metadata))
    if conflicts:
        raise ValueError(f"Post-match metadata cannot override reserved fields: {conflicts}")
    root = settings.data_path / "archive" / str(settings.season_id) / f"gw{int(gameweek)}"
    idempotency_key = str(extra_metadata.get("idempotency_key", "")).strip()
    if idempotency_key:
        for existing in root.glob("post_match_*"):
            manifest_path = existing / "manifest.json"
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if previous.get("idempotency_key") != idempotency_key:
                continue
            for name in ("player_results.parquet", "coach_results.parquet"):
                path = existing / name
                expected = previous.get("sha256", {}).get(name)
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Existing idempotent post-match archive is corrupted: {path}")
            registry_path = existing.parent / "registry" / f"{existing.name}.json"
            if not registry_path.is_file():
                raise ValueError("Existing idempotent post-match archive has no registry record.")
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            if registry.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
                raise ValueError("Existing idempotent post-match archive registry hash mismatch.")
            return existing
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / f"post_match_{stamp}_{uuid4().hex[:8]}"
    with _atomic_new_directory(out) as staging_dir:
        player_results.to_parquet(staging_dir / "player_results.parquet", index=False)
        coach_results.to_parquet(staging_dir / "coach_results.parquet", index=False)
        payloads = {}
        for name in ("player_results.parquet", "coach_results.parquet"):
            payloads[name] = hashlib.sha256((staging_dir / name).read_bytes()).hexdigest()
        manifest = {
            "season_id": settings.season_id,
            "dunkest_gameweek": int(gameweek),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "schema_version": 3 if idempotency_key else 2,
            **_code_provenance(settings),
            "sha256": payloads,
        }
        manifest.update(extra_metadata)
        (staging_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    manifest_path = out / "manifest.json"
    registry_dir = out.parent / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_path = registry_dir / f"{out.name}.json"
    registry = {
        "schema_version": 1,
        "archive_id": out.name,
        "season_id": str(settings.season_id),
        "dunkest_gameweek": int(gameweek),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "sha256": payloads,
        "idempotency_key": idempotency_key or None,
    }
    registry_created = False
    try:
        with registry_path.open("x", encoding="utf-8") as stream:
            registry_created = True
            stream.write(json.dumps(registry, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if registry_created:
            registry_path.unlink(missing_ok=True)
        shutil.rmtree(out, ignore_errors=True)
        raise
    return out
