#!/usr/bin/env python3
"""Verify an archived pre-lock bundle and independently recheck source freshness."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from archive_dunkest_pre_lock_run_v1 import (
    digest, inventory, load_json, freshness_report, fixture_mapping_validation,
    snapshot_content_validation, player_forecast_snapshot_validation,
    versioned_forecast_snapshot_validation,
)

def review(archive_dir: Path, max_hours: float = 36.0) -> dict:
    archive_dir = archive_dir.resolve()
    meta_path = archive_dir / "archive_manifest.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Archive manifest missing: {meta_path}")
    meta = load_json(meta_path)
    actual_files = inventory(archive_dir)
    expected_files = meta.get("files", [])
    integrity_ok = actual_files == expected_files
    if not integrity_ok:
        raise ValueError("Archived file hashes do not match archive manifest")
    registry_path = archive_dir.parents[2] / "registry" / f"{meta.get('run_id')}.json"
    if not registry_path.is_file():
        raise ValueError("Immutable archive registry record is missing")
    registry = load_json(registry_path)
    if registry.get("archive_manifest_sha256") != digest(meta_path):
        raise ValueError("Archive manifest hash does not match the immutable registry")
    registry_hashes = [
        ("predictions.parquet", "predictions_sha256", True),
        ("lineups.parquet", "lineups_sha256", True),
    ]
    if int(meta.get("schema_version", 1) or 1) >= 2:
        registry_hashes.extend([
            ("player_forecast_snapshot.parquet", "player_forecast_snapshot_sha256", False),
            ("runtime_feature_snapshot.parquet", "runtime_feature_snapshot_sha256", False),
            ("shadow_forecast_snapshot.parquet", "shadow_forecast_snapshot_sha256", False),
            ("coach_forecast_snapshot.parquet", "coach_forecast_snapshot_sha256", False),
        ])
    else:
        # Older registries may contain the first-generation player/runtime
        # snapshots, but did not require them. Verify only hashes they recorded.
        registry_hashes.extend([
            (filename, field, False) for filename, field in (
                ("player_forecast_snapshot.parquet", "player_forecast_snapshot_sha256"),
                ("runtime_feature_snapshot.parquet", "runtime_feature_snapshot_sha256"),
            ) if field in registry
        ])
    for filename, field, required in registry_hashes:
        path = archive_dir / filename
        expected = registry.get(field)
        if expected is None:
            if required or path.exists():
                raise ValueError(f"{filename} is missing its immutable registry hash")
        elif not path.is_file() or expected != digest(path):
            raise ValueError(f"{filename} hash does not match the immutable registry")
    run_manifest = load_json(archive_dir / "manifest.json")
    current_freshness = freshness_report(archive_dir, run_manifest, max_hours)
    current_content_validation = snapshot_content_validation(archive_dir, run_manifest)
    current_forecast_validation = player_forecast_snapshot_validation(archive_dir, run_manifest)
    current_snapshot_bundle_validation = versioned_forecast_snapshot_validation(archive_dir, run_manifest)
    current_fixture_validation = fixture_mapping_validation(archive_dir, run_manifest, max_hours)
    current_eligible = (
        integrity_ok
        and bool(meta.get("pre_lock_eligible", False))
        and bool(registry.get("pre_lock_eligible", False))
        and all(x["status"] == "fresh" for x in current_freshness)
        and all(x["status"] == "valid" for x in current_content_validation)
        and current_forecast_validation.get("status") == "valid"
        and current_snapshot_bundle_validation.get("status") == "complete"
        and current_fixture_validation.get("status") == "verified"
        and run_manifest.get("archive_status", "complete") == "complete"
        and not run_manifest.get("persistence_errors")
    )
    snapshot_status = current_snapshot_bundle_validation.get("status", "unverifiable")
    required_inputs = run_manifest.get("required_pre_match_inputs", {})
    market_input = required_inputs.get("dunkest_market_snapshot", {})
    market_input_missing = (
        isinstance(market_input, dict) and market_input.get("status") == "missing"
    )
    if current_eligible:
        review_status = "verified_pre_lock"
    elif market_input_missing:
        review_status = "incomplete"
    elif snapshot_status in {"legacy", "incomplete", "unverifiable", "mapping_ambiguous"}:
        review_status = snapshot_status
    else:
        review_status = "not_pre_lock_eligible"
    return {
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": meta.get("run_id"),
        "archive_path": str(archive_dir),
        "integrity_ok": integrity_ok,
        "status": review_status,
        "stored_eligibility_status": meta.get("eligibility_status"),
        "stored_pre_lock_eligible": bool(meta.get("pre_lock_eligible", False)),
        "stored_snapshot_freshness": meta.get("snapshot_freshness", []),
        "rechecked_snapshot_freshness": current_freshness,
        "rechecked_snapshot_content_validation": current_content_validation,
        "rechecked_player_forecast_snapshot_validation": current_forecast_validation,
        "rechecked_versioned_forecast_snapshot_validation": current_snapshot_bundle_validation,
        "rechecked_fixture_mapping_validation": current_fixture_validation,
        "rechecked_required_pre_match_inputs": required_inputs,
        "rechecked_pre_lock_eligible": bool(current_eligible),
        "note": "This review is separate and read-only. Eligibility requires intact hashes, fresh snapshots, a verified fixture mapping, and an all-candidate forecast tied to a sourced exact Dunkest lock time.",
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--max-age-hours", type=float, default=36.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = review(args.archive_dir, args.max_age_hours)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            parser.error(f"Refusing to overwrite review artifact: {args.output}")
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")

if __name__ == "__main__":
    main()
