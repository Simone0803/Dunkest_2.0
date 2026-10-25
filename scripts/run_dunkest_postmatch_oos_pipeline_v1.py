#!/usr/bin/env python3
"""Collect verified post-match outcomes and evaluate one immutable pre-lock run."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from archive_dunkest_pre_lock_run_v1 import (
    digest, inventory, load_json, versioned_forecast_snapshot_validation,
)

def validate_archive(archive_dir: Path, allow_ineligible: bool = False) -> dict:
    archive_dir = archive_dir.resolve()
    meta_path = archive_dir / "archive_manifest.json"
    if not meta_path.is_file():
        raise ValueError(f"Not a pre-lock archive: {archive_dir}")
    meta = load_json(meta_path)
    if inventory(archive_dir) != meta.get("files", []):
        raise ValueError("Archived run failed SHA-256 integrity verification")
    registry_path = archive_dir.parents[2] / "registry" / f"{meta.get('run_id')}.json"
    if not registry_path.is_file():
        raise ValueError("Immutable archive registry record is missing")
    registry = load_json(registry_path)
    if registry.get("archive_manifest_sha256") != digest(meta_path):
        raise ValueError("Archive manifest hash does not match the immutable registry")
    if registry.get("predictions_sha256") != digest(archive_dir / "predictions.parquet"):
        raise ValueError("Frozen prediction hash does not match the immutable registry")
    if registry.get("lineups_sha256") != digest(archive_dir / "lineups.parquet"):
        raise ValueError("Frozen lineup hash does not match the immutable registry")
    archive_schema = int(meta.get("schema_version", 1) or 1)
    if archive_schema >= 2:
        registry_snapshots = (
            ("player_forecast_snapshot.parquet", "player_forecast_snapshot_sha256"),
            ("runtime_feature_snapshot.parquet", "runtime_feature_snapshot_sha256"),
            ("shadow_forecast_snapshot.parquet", "shadow_forecast_snapshot_sha256"),
            ("coach_forecast_snapshot.parquet", "coach_forecast_snapshot_sha256"),
        )
    else:
        registry_snapshots = ((
            "player_forecast_snapshot.parquet", "player_forecast_snapshot_sha256"
        ),) if "player_forecast_snapshot_sha256" in registry else ()
    for filename, field in registry_snapshots:
        path = archive_dir / filename
        expected = registry.get(field)
        if expected is None:
            if path.exists():
                raise ValueError(f"Frozen {filename} has no immutable registry hash")
        elif not path.is_file() or expected != digest(path):
            raise ValueError(f"Frozen {filename} hash does not match the immutable registry")
    if bool(registry.get("pre_lock_eligible")) != bool(meta.get("pre_lock_eligible")):
        raise ValueError("Archive eligibility differs from the immutable registry")
    run_manifest = load_json(archive_dir / "manifest.json")
    if not (archive_dir / "predictions.parquet").is_file() or not (archive_dir / "lineups.parquet").is_file():
        raise ValueError("Archived predictions or lineups are missing")
    try:
        run_schema = int(run_manifest.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        raise ValueError("Archived run manifest has an invalid schema version") from None
    snapshot_validation = versioned_forecast_snapshot_validation(archive_dir, run_manifest)
    if run_schema >= 2 and snapshot_validation.get("status") != "complete":
        raise ValueError(
            "Archived versioned forecast snapshots are incomplete or unverifiable; "
            "they cannot enter post-match evaluation"
        )
    if not meta.get("pre_lock_eligible", False) and not allow_ineligible:
        raise ValueError("Archive is not certified pre-lock evidence; use --allow-ineligible-diagnostic only for exploratory evaluation")
    return {
        "archive_manifest": meta,
        "run_manifest": run_manifest,
        "forecast_snapshot_validation": snapshot_validation,
    }

def run_pipeline(archive_dir: Path, data_dir: Path, output_dir: Path, allow_partial: bool = False,
                 allow_ineligible: bool = False) -> dict:
    archive_dir = archive_dir.resolve()
    data_dir = data_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checked = validate_archive(archive_dir, allow_ineligible)
    config = checked["run_manifest"].get("configuration", {})
    season_id = str(config.get("season_id", ""))
    gameweek = int(config.get("target_gameweek", -1))
    if not season_id or gameweek < 1:
        raise ValueError("Archived run lacks season_id or target_gameweek")
    collection_dir = output_dir / "collection"
    evaluation_dir = output_dir / "evaluation"
    collect_cmd = [sys.executable, str(ROOT / "scripts/build_dunkest_post_match_results_v1.py"),
                   "--data-dir", str(data_dir), "--run-dir", str(archive_dir),
                   "--output-dir", str(collection_dir)]
    if allow_partial:
        collect_cmd.append("--allow-partial")
    collected = subprocess.run(collect_cmd, cwd=ROOT, text=True, capture_output=True)
    collection_result = None
    try:
        collection_result = json.loads(collected.stdout)
    except (ValueError, json.JSONDecodeError):
        pass
    if collected.returncode != 0:
        if not (allow_partial and collection_result and collection_result.get("archive")):
            raise RuntimeError("Post-match collection is not complete/ready. See collection output: " +
                               (collected.stderr[-2000:] or collected.stdout[-2000:]))
    results_dir = collection_result.get("archive") if collection_result else None
    if not results_dir:
        raise RuntimeError("Collector did not return an immutable results archive path")
    evaluate_cmd = [sys.executable, str(ROOT / "scripts/evaluate_archived_run_post_match_v1.py"),
                    "--data-dir", str(data_dir), "--season-id", season_id, "--gameweek", str(gameweek),
                    "--run-dir", str(archive_dir), "--results-dir", str(results_dir),
                    "--output-dir", str(evaluation_dir)]
    evaluated = subprocess.run(evaluate_cmd, cwd=ROOT, text=True, capture_output=True)
    if evaluated.stdout:
        print(evaluated.stdout)
    if evaluated.returncode != 0:
        raise RuntimeError("Post-match evaluation did not reach ready status: " + (evaluated.stderr[-2000:] or evaluated.stdout[-2000:]))
    try:
        evaluation_result = json.loads(evaluated.stdout)
    except json.JSONDecodeError:
        evaluation_result = {"status": "see_evaluation_artifacts"}
    return {"status": "completed", "run_id": checked["run_manifest"].get("run_id"),
            "season_id": season_id, "gameweek": gameweek,
            "collection": collection_result, "evaluation": evaluation_result,
            "evaluation_dir": str(evaluation_dir)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/backtest/postmatch_pipeline")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--allow-ineligible-diagnostic", action="store_true")
    args = parser.parse_args()
    try:
        result = run_pipeline(args.archive_dir, args.data_dir, args.output_dir,
                              args.allow_partial, args.allow_ineligible_diagnostic)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"post-match pipeline stopped: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
