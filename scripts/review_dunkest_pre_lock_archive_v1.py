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
    snapshot_content_validation
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
    run_manifest = load_json(archive_dir / "manifest.json")
    current_freshness = freshness_report(archive_dir, run_manifest, max_hours)
    current_content_validation = snapshot_content_validation(archive_dir, run_manifest)
    current_fixture_validation = fixture_mapping_validation(archive_dir, run_manifest, max_hours)
    current_eligible = (
        integrity_ok
        and all(x["status"] == "fresh" for x in current_freshness)
        and all(x["status"] == "valid" for x in current_content_validation)
        and current_fixture_validation.get("status") == "verified"
    )
    return {
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": meta.get("run_id"),
        "archive_path": str(archive_dir),
        "integrity_ok": integrity_ok,
        "stored_eligibility_status": meta.get("eligibility_status"),
        "stored_pre_lock_eligible": bool(meta.get("pre_lock_eligible", False)),
        "stored_snapshot_freshness": meta.get("snapshot_freshness", []),
        "rechecked_snapshot_freshness": current_freshness,
        "rechecked_snapshot_content_validation": current_content_validation,
        "rechecked_fixture_mapping_validation": current_fixture_validation,
        "rechecked_pre_lock_eligible": bool(current_eligible),
        "note": "This review is a separate audit record. Eligibility requires intact hashes, fresh snapshots, and a verified fixture mapping; it does not mutate the archive or immutable registry.",
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
