from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
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
    """Fingerprint source code so an artifact remains attributable without Git."""
    source_root = settings.root / "src"
    digest = hashlib.sha256()
    files = sorted(source_root.rglob("*.py")) if source_root.is_dir() else []
    for path in files:
        relative = path.relative_to(settings.root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "python_files": len(files)}


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _input_paths(settings: Settings) -> list[Path]:
    processed = settings.data_path / "processed"
    log_season = settings.feature_season if settings.target_gameweek == 1 else settings.season
    paths = [
        processed / f"player_game_logs_{log_season}.parquet",
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
        processed / "player_game_logs_2025-26.parquet",
        settings.data_path / "raw" / "nba_historical_logs_2018-25_v1" / "collection_manifest.json",
        settings.data_path / "current_lineups_market.csv",
        settings.data_path / "lineups_availability.csv",
        settings.data_path / "injury_overrides.csv",
        settings.data_path / "rookie_college.csv",
        settings.root / "config" / "nba_coaches_2026.yaml",
        settings.root / "config" / "dunkest_coaches_2026-27.csv",
    ]
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
        "season_id", "dunkest_gameweek", "retrieved_at_utc", "source", "schema_version", "sha256"
    }
    conflicts = sorted(reserved_fields.intersection(extra_metadata))
    if conflicts:
        raise ValueError(f"Post-match metadata cannot override reserved fields: {conflicts}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = settings.data_path / "archive" / str(settings.season_id) / f"gw{int(gameweek)}" / f"post_match_{stamp}_{uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=False)
    player_results.to_parquet(out / "player_results.parquet", index=False)
    coach_results.to_parquet(out / "coach_results.parquet", index=False)
    payloads = {}
    for name in ("player_results.parquet", "coach_results.parquet"):
        payloads[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    manifest = {
        "season_id": settings.season_id,
        "dunkest_gameweek": int(gameweek),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "schema_version": 1,
        "sha256": payloads,
    }
    manifest.update(extra_metadata)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
