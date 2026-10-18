#!/usr/bin/env python3
"""Create an immutable, hash-verified archive of a Dunkest prediction run."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "data/archives/pre_lock"
RUN_FILES = ("manifest.json", "predictions.parquet", "lineups.parquet")
# The current scraper's authoritative availability source is the timestamped
# official injuries snapshot. lineups_availability.csv is a legacy artifact no
# longer written by the current Lineups browser flow, so requiring it would make
# every new capture depend on a stale, unused CSV.
SNAPSHOTS = (
    "current_lineups_market.csv",
    "player_credits_26_gw1.parquet", "injuries_26_gw1.parquet",
    "coach_market_26_gw1.parquet",
    "dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet",
)
FRESHNESS_REQUIRED = set(SNAPSHOTS) - {
    "dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet"
}

def snapshot_names(manifest: dict) -> tuple[str, ...]:
    """Resolve required snapshot filenames for the run season and gameweek."""
    config = manifest.get("configuration", {})
    season = str(manifest.get("season_id") or config.get("season_id") or "")
    gameweek = manifest.get("target_gameweek", config.get("target_gameweek"))
    try:
        gameweek = int(gameweek)
    except (TypeError, ValueError):
        gameweek = 0
    if not season or season == "unknown" or gameweek < 1:
        return SNAPSHOTS
    return (
        "current_lineups_market.csv",
        f"player_credits_{season}_gw{gameweek}.parquet",
        f"injuries_{season}_gw{gameweek}.parquet",
        f"coach_market_{season}_gw{gameweek}.parquet",
        f"dunkest_fixture_mapping_{season}_lineups_browser_gw{gameweek}_team_status_v2.parquet",
    )

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value

def utc(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def inventory(root: Path) -> list[dict]:
    result = []
    for item in sorted(root.rglob("*")):
        if item.is_file() and item.name != "archive_manifest.json":
            result.append({"path": item.relative_to(root).as_posix(),
                           "size_bytes": item.stat().st_size, "sha256": digest(item)})
    return result
def freshness_report(run_dir: Path, manifest: dict, max_hours: float) -> list[dict]:
    snap = run_dir / "pre_match_snapshot"
    run_time = utc(manifest.get("timestamp"))
    result = []
    inputs = manifest.get("inputs", [])
    for name in snapshot_names(manifest):
        path = snap / name
        if not path.is_file():
            result.append({"path": name, "status": "missing", "age_hours": None})
            continue
        meta = None
        sidecar = snap / f"{name}.meta.json"
        if sidecar.is_file():
            try:
                meta = load_json(sidecar)
            except (OSError, ValueError, json.JSONDecodeError):
                meta = None
        if not isinstance(meta, dict):
            for row in inputs:
                source = str(row.get("path", ""))
                if source.endswith("/" + name) or source == name:
                    meta = row.get("cache_metadata")
                    break
        fetched = utc((meta or {}).get("fetched_at") if isinstance(meta, dict) else None)
        # Fixture mappings embed source_retrieved_at_utc per fixture. The file
        # mtime or validation-decision timestamp is not a substitute for this
        # source observation timestamp.
        if fetched is None and name.startswith("dunkest_fixture_mapping_"):
            try:
                import pandas as pd
                mapping = pd.read_parquet(path)
                gw = manifest.get("target_gameweek", manifest.get("configuration", {}).get("target_gameweek"))
                if gw is not None and {"dunkest_gameweek", "source_retrieved_at_utc", "mapping_verified"}.issubset(mapping.columns):
                    mapping = mapping.loc[
                        pd.to_numeric(mapping["dunkest_gameweek"], errors="coerce").eq(int(gw))
                        & mapping["mapping_verified"].fillna(False).astype(bool)
                    ]
                    retrieved = pd.to_datetime(mapping["source_retrieved_at_utc"], utc=True, errors="coerce")
                    if not mapping.empty and retrieved.notna().all():
                        fetched = retrieved.min().to_pydatetime().astimezone(timezone.utc)
            except Exception:
                fetched = None
        if fetched is None:
            status, age = "unknown_freshness", None
        elif run_time is None:
            status, age = "unknown_run_timestamp", None
        else:
            age = (run_time - fetched).total_seconds() / 3600
            if age < -0.01:
                status = "fetched_after_prediction"
            elif age > max_hours:
                status = "stale"
            else:
                status = "fresh"
        result.append({"path": name, "status": status,
                       "age_hours": round(age, 4) if age is not None else None,
                       "fetched_at": fetched.isoformat() if fetched else None})
    return sorted(result, key=lambda row: row["path"])

def snapshot_content_validation(run_dir: Path, manifest: dict) -> list[dict]:
    """Check that required snapshot files contain plausible, round-linked data.

    This is a structural gate, not proof that the source is historically complete.
    It deliberately keeps failed runs archivable for diagnosis, but never eligible.
    """
    import pandas as pd

    config = manifest.get("configuration", {})
    season = str(manifest.get("season_id") or config.get("season_id") or "")
    gw = int(manifest.get("target_gameweek", config.get("target_gameweek", 0)) or 0)
    snap = run_dir / "pre_match_snapshot"
    names = snapshot_names(manifest)
    results: list[dict] = []
    specs = {
        "current_lineups_market.csv": ({"player_name", "cr", "team", "role"}, 400, "player_name", {"cr", "team", "role"}),
        f"player_credits_{season}_gw{gw}.parquet": ({"player_name", "team_code", "role", "cr", "gameweek"}, 400, "player_name", {"team_code", "role", "cr", "gameweek"}),
        f"coach_market_{season}_gw{gw}.parquet": ({"coach", "team", "coach_cr", "opponent", "opponent_coach", "opponent_coach_cr", "gameweek"}, 30, "team", {"coach", "coach_cr", "opponent", "opponent_coach", "opponent_coach_cr", "gameweek"}),
        f"injuries_{season}_gw{gw}.parquet": ({"player_name", "status", "team", "gameweek"}, 0, "player_name", {"status", "team", "gameweek"}),
    }
    for name in names:
        path = snap / name
        if not path.is_file():
            results.append({"path": name, "status": "missing", "row_count": None, "errors": ["file missing"]})
            continue
        if name.startswith("dunkest_fixture_mapping_"):
            # Detailed fixture identity, kickoff, hash and cutoff checks live below.
            continue
        spec = specs.get(name)
        if spec is None:
            results.append({"path": name, "status": "invalid", "row_count": None, "errors": ["no content-validation rule defined"]})
            continue
        required, min_rows, unique_key, nonnull = spec
        try:
            frame = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path)
        except Exception as exc:
            results.append({"path": name, "status": "invalid", "row_count": None, "errors": [f"cannot read snapshot: {exc}"]})
            continue
        errors = []
        missing_cols = sorted(required - set(frame.columns))
        if missing_cols:
            errors.append(f"required columns missing: {missing_cols}")
        if len(frame) < min_rows:
            errors.append(f"too few rows: {len(frame)} < {min_rows}")
        key_cols = (unique_key,) if isinstance(unique_key, str) else tuple(unique_key)
        if all(col in frame.columns for col in key_cols):
            key_frame = frame.loc[:, list(key_cols)].fillna("").astype(str)
            if key_frame.apply(lambda col: col.str.strip().eq("")).any(axis=None):
                errors.append(f"blank values in identity columns {list(key_cols)}")
            if name != "current_lineups_market.csv" and key_frame.duplicated().any():
                errors.append(f"duplicate identity values for {list(key_cols)}")
        for col in sorted(nonnull & set(frame.columns)):
            if frame[col].isna().any():
                errors.append(f"null values in required column {col}")
        if name == f"player_credits_{season}_gw{gw}.parquet" and "gameweek" in frame.columns:
            values = pd.to_numeric(frame["gameweek"], errors="coerce")
            if values.isna().any() or not values.eq(gw).all():
                errors.append("player credits contain rows not linked to target gameweek")
        if name == f"coach_market_{season}_gw{gw}.parquet" and "gameweek" in frame.columns:
            values = pd.to_numeric(frame["gameweek"], errors="coerce")
            if values.isna().any() or not values.eq(gw).all():
                errors.append("coach market contains rows not linked to target gameweek")
            if "team" in frame.columns and frame["team"].nunique(dropna=True) < 30:
                errors.append("coach market does not cover all 30 NBA teams")
        if name == f"injuries_{season}_gw{gw}.parquet" and "gameweek" in frame.columns and not frame.empty:
            values = pd.to_numeric(frame["gameweek"], errors="coerce")
            if values.isna().any() or not values.eq(gw).all():
                errors.append("injury snapshot contains rows not linked to target gameweek")
        if name == "lineups_availability.csv" and "observed_at_utc" in frame.columns and not frame.empty:
            observed = pd.to_datetime(frame["observed_at_utc"], utc=True, errors="coerce")
            run_time = pd.to_datetime(manifest.get("timestamp"), utc=True, errors="coerce")
            if observed.isna().any():
                errors.append("availability rows lack valid observation timestamps")
            elif not pd.isna(run_time) and (observed > run_time + pd.Timedelta(minutes=5)).any():
                errors.append("availability observation occurs after prediction timestamp")
        results.append({"path": name, "status": "valid" if not errors else "invalid",
                        "row_count": int(len(frame)), "errors": errors})
    return sorted(results, key=lambda row: row["path"])


def fixture_mapping_validation(run_dir: Path, manifest: dict, max_hours: float) -> dict:
    """Validate fixture identity and cutoff provenance before certifying an archive."""
    import pandas as pd

    config = manifest.get("configuration", {})
    season = str(manifest.get("season_id") or config.get("season_id") or "")
    gw = int(manifest.get("target_gameweek", config.get("target_gameweek", 0)) or 0)
    run_time = pd.to_datetime(manifest.get("timestamp"), utc=True, errors="coerce")
    snap = run_dir / "pre_match_snapshot"
    files = list(snap.glob(f"dunkest_fixture_mapping_{season}_*.parquet"))
    errors: list[str] = []
    if len(files) != 1:
        return {"status": "invalid", "errors": [f"expected exactly one fixture mapping; found {len(files)}"]}
    try:
        mapping = pd.read_parquet(files[0])
    except Exception as exc:
        return {"status": "invalid", "errors": [f"cannot read fixture mapping: {exc}"]}
    required = {"nba_game_id", "game_datetime_utc", "dunkest_gameweek", "fantasy_eligible", "mapping_verified", "source_retrieved_at_utc", "raw_payload_sha256"}
    missing = sorted(required - set(mapping.columns))
    if missing:
        return {"status": "invalid", "errors": [f"fixture mapping missing columns: {missing}"]}
    target = mapping.loc[pd.to_numeric(mapping["dunkest_gameweek"], errors="coerce").eq(gw)].copy()
    eligible = target.loc[target["fantasy_eligible"].fillna(False).astype(bool)].copy()
    if eligible.empty:
        errors.append("no fantasy-eligible fixtures for target gameweek")
    if not eligible.empty:
        if eligible["nba_game_id"].astype(str).duplicated().any():
            errors.append("duplicate NBA fixture IDs")
        if not eligible["mapping_verified"].fillna(False).astype(bool).all():
            errors.append("one or more fantasy-eligible fixture mappings are unverified")
        hashes = eligible["raw_payload_sha256"].fillna("").astype(str).str.strip()
        if hashes.eq("").any() or hashes.str.lower().isin({"nan", "none"}).any():
            errors.append("one or more fixture rows lack raw payload hashes")
        kickoffs = pd.to_datetime(eligible["game_datetime_utc"], utc=True, errors="coerce")
        retrieved = pd.to_datetime(eligible["source_retrieved_at_utc"], utc=True, errors="coerce")
        if kickoffs.isna().any():
            errors.append("one or more fixtures lack valid UTC kickoffs")
        if retrieved.isna().any():
            errors.append("one or more fixture source retrieval timestamps are missing/invalid")
        if not kickoffs.isna().any() and not retrieved.isna().any():
            earliest_kickoff = kickoffs.min()
            # The mapping is a single Giornata-level calendar capture. Its
            # freshness window is anchored to the first kickoff, not each later
            # Turno's kickoff; otherwise a valid pre-lock capture is guaranteed
            # to fail for fixtures scheduled on subsequent days.
            if (retrieved > earliest_kickoff).any():
                errors.append("fixture mapping source was retrieved at or after the earliest kickoff")
            mapping_age_at_first_kickoff = (
                earliest_kickoff - retrieved
            ).dt.total_seconds()
            if (mapping_age_at_first_kickoff > max_hours * 3600).any():
                errors.append("fixture mapping source snapshot is older than the permitted pre-lock window relative to earliest kickoff")
            if pd.isna(run_time):
                errors.append("prediction run has no valid UTC timestamp")
            else:
                if (retrieved > run_time + pd.Timedelta(minutes=5)).any():
                    errors.append("fixture mapping source was retrieved after the prediction run")
                hours_to_kickoff = (earliest_kickoff - run_time).total_seconds() / 3600
                if not (0 <= hours_to_kickoff <= max_hours):
                    errors.append(f"prediction run is {hours_to_kickoff:.2f} hours before earliest kickoff; expected 0–{max_hours:.2f}")
        return {"status": "verified" if not errors else "invalid", "errors": errors,
                "fixture_count": int(len(eligible)),
                "earliest_kickoff_utc": None if kickoffs.isna().any() else kickoffs.min().isoformat(),
                "mapping_file": files[0].name}
    return {"status": "invalid", "errors": errors, "fixture_count": 0, "mapping_file": files[0].name}


def archive_run(run_dir: Path, archive_root: Path, max_hours: float = 36.0) -> dict:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    missing = [name for name in RUN_FILES if not (run_dir / name).is_file()]
    if missing:
        raise ValueError(f"Run artifacts missing: {missing}")
    manifest = load_json(run_dir / "manifest.json")
    run_id = str(manifest.get("run_id") or run_dir.name)
    if run_id != run_dir.name:
        raise ValueError("Run ID differs from its directory name")
    config = manifest.get("configuration", {})
    season = str(manifest.get("season_id") or config.get("season_id") or "unknown")
    gw = manifest.get("target_gameweek", config.get("target_gameweek"))
    if gw is None:
        raise ValueError("Target gameweek missing from manifest")
    snap_status = freshness_report(run_dir, manifest, max_hours)
    missing_snapshots = [x["path"] for x in snap_status if x["status"] == "missing"]
    if missing_snapshots:
        raise ValueError(f"Required pre-match snapshots missing: {missing_snapshots}")
    content_validation = snapshot_content_validation(run_dir, manifest)
    fixture_validation = fixture_mapping_validation(run_dir, manifest, max_hours)
    eligible = (
        all(x["status"] == "fresh" for x in snap_status)
        and all(x["status"] == "valid" for x in content_validation)
        and fixture_validation["status"] == "verified"
    )
    dest = archive_root / f"season_id={season}" / f"gw={int(gw)}" / run_id
    registry_dir = archive_root / "registry"
    registry_path = registry_dir / f"{run_id}.json"
    archive_root.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        staging_parent = Path(tempfile.mkdtemp(prefix=f".{run_id}.stage.", dir=dest.parent))
        staging = staging_parent / run_id
        try:
            shutil.copytree(run_dir, staging, copy_function=shutil.copy2)
            before = inventory(run_dir)
            after = inventory(staging)
            if before != after:
                raise RuntimeError("Source run changed during copy; archive not published")
            archive_meta = {
                "schema_version": 1, "run_id": run_id,
                "archived_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_run_dir": str(run_dir),
                "source_manifest_sha256": digest(run_dir / "manifest.json"),
                "max_snapshot_age_hours": max_hours,
                "snapshot_freshness": snap_status,
                "snapshot_content_validation": content_validation,
                "fixture_mapping_validation": fixture_validation,
                "pre_lock_eligible": bool(eligible),
                "eligibility_status": "verified_fresh" if eligible else "incomplete_evidence",
                "files": after,
            }
            (staging / "archive_manifest.json").write_text(
                json.dumps(archive_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if dest.exists():
                raise FileExistsError(f"Archive destination already exists: {dest}")
            os.rename(staging, dest)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        archive_status = "archived"
    else:
        archive_meta = load_json(dest / "archive_manifest.json")
        if inventory(dest) != archive_meta.get("files", []):
            raise ValueError(f"Existing archive integrity check failed: {dest}")
        archive_status = "already_archived_verified"
    archive_meta = load_json(dest / "archive_manifest.json")
    record = {
        "schema_version": 1, "run_id": run_id, "season_id": season, "gameweek": int(gw),
        "run_timestamp": manifest.get("timestamp"),
        "archive_path": str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest),
        "archive_manifest_sha256": digest(dest / "archive_manifest.json"),
        "pre_lock_eligible": bool(archive_meta.get("pre_lock_eligible")),
        "eligibility_status": archive_meta.get("eligibility_status"),
        "snapshot_freshness": archive_meta.get("snapshot_freshness", []),
        "predictions_sha256": digest(dest / "predictions.parquet"),
        "lineups_sha256": digest(dest / "lineups.parquet"),
    }
    # Keep older immutable registry records idempotent: only new archive schema
    # versions carry the structural-content validation field.
    if "snapshot_content_validation" in archive_meta:
        record["snapshot_content_validation"] = archive_meta["snapshot_content_validation"]
    archive_created = archive_status == "archived"
    if registry_path.exists():
        if load_json(registry_path) != record:
            if archive_created:
                shutil.rmtree(dest, ignore_errors=True)
            raise ValueError(f"Immutable registry record differs: {registry_path}")
        registry_status = "already_registered_verified"
    else:
        registry_created = False
        try:
            with registry_path.open("x", encoding="utf-8") as stream:
                registry_created = True
                stream.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            if registry_created:
                registry_path.unlink(missing_ok=True)
            if archive_created:
                shutil.rmtree(dest, ignore_errors=True)
            raise
        registry_status = "registered"
    return {"status": archive_status, "registry_status": registry_status,
            "run_id": run_id, "archive_path": str(dest), "registry_path": str(registry_path),
            "pre_lock_eligible": record["pre_lock_eligible"],
            "eligibility_status": record["eligibility_status"],
            "snapshot_freshness": record["snapshot_freshness"]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--max-age-hours", type=float, default=36.0)
    args = parser.parse_args()
    if bool(args.run_id) == bool(args.run_dir):
        parser.error("provide exactly one of --run-id and --run-dir")
    source = args.run_dir if args.run_dir else ROOT / "data/predictions" / args.run_id
    try:
        result = archive_run(source, args.archive_root.resolve(), args.max_age_hours)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"archive failed: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
