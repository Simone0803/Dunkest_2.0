from __future__ import annotations

import hashlib
import json
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

import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import read_cache_metadata
from dunkest.data.dunkest.fixtures import check_backtest_readiness
from dunkest.optimize.milp import (
    LineupSolution,
    TEAM_PLAYER_SCORE_CORRELATION,
)


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


def save_run_artifacts(
    settings: Settings,
    predictions: pd.DataFrame,
    solutions: list[LineupSolution],
    models: dict | None = None,
    run_metadata: dict | None = None,
) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    out_dir = settings.data_path / "predictions" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    predictions.to_parquet(out_dir / "predictions.parquet", index=False)
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
        f"player_credits_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"coach_market_{settings.season_id}_gw{settings.target_gameweek}.parquet",
        f"injuries_{settings.season_id}_gw{settings.target_gameweek}.parquet",
    }
    processed_dir = settings.data_path / "processed"
    snapshot_paths = [processed_dir / name for name in snapshot_names]
    snapshot_paths.extend(sorted(processed_dir.glob(f"dunkest_fixture_mapping_{settings.season_id}_*.parquet")))
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
    for source_path in sorted(snapshot_paths, key=str):
        if not source_path.is_file():
            continue
        destination = snapshot_dir / source_path.name
        shutil.copy2(source_path, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        snapshot_files.append({"path": destination.name, "sha256": digest, "source": str(source_path)})

    fitted_models = models or {}
    git_hash = _git_hash()
    input_fingerprints = _input_fingerprints(settings)
    configuration = asdict(settings)
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_hash": git_hash,
        "git_hash_unavailable_reason": (
            None if git_hash else "No resolvable commit is available; source_fingerprint identifies src/ instead."
        ),
        "git_branch": _git_branch(),
        "source_fingerprint": _source_fingerprint(settings),
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
        },
        "model_details": {
            "effective_models": sorted(
                key for key in fitted_models if not key.startswith("_")
            ),
            "feature_columns": fitted_models.get("_feature_cols", []),
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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        settings.data_path / "archive" / str(settings.season_id) / f"gw{int(gameweek)}"
        / f"post_match_{stamp}_{uuid4().hex[:8]}"
    )
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
            "schema_version": 2,
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
