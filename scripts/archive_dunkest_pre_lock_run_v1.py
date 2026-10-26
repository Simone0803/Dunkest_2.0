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

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "data/archives/pre_lock"
RUN_FILES = ("manifest.json", "predictions.parquet", "lineups.parquet")
# The current scraper's authoritative availability source is the timestamped
# official injuries snapshot. lineups_availability.csv is a legacy artifact no
# longer written by the current Lineups browser flow, so requiring it would make
# every new capture depend on a stale, unused CSV.
SNAPSHOTS = (
    "current_lineups_market.csv",
    "dunkest_players_26_gw1.parquet",
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
        f"dunkest_players_{season}_gw{gameweek}.parquet",
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


def _manifest_schema_version(manifest: dict) -> int | None:
    try:
        return int(manifest.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        return None

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
        f"dunkest_players_{season}_gw{gw}.parquet": ({"player_name", "cr", "team_code", "position"}, 400, "player_name", {"cr", "team_code", "position"}),
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


def runtime_feature_snapshot_validation(run_dir: Path, manifest: dict, forecasts=None) -> dict:
    """Verify hash, candidate coverage and unambiguous runtime feature linkage."""
    import pandas as pd

    descriptor = manifest.get("runtime_feature_snapshot", {})
    manifest_schema = _manifest_schema_version(manifest)
    if manifest_schema is None:
        return {"status": "invalid", "errors": ["run manifest schema version is invalid"]}
    if manifest_schema >= 2:
        expected_schema = manifest.get("snapshot_schemas", {}).get("runtime_features")
        if expected_schema != 1 or descriptor.get("schema_version") != expected_schema:
            return {
                "status": "invalid",
                "errors": ["runtime feature snapshot schema version is missing or unsupported"],
            }
    path = run_dir / "runtime_feature_snapshot.parquet"
    errors = []
    if descriptor.get("certification_status") != "valid":
        errors.append("runtime feature snapshot is not marked structurally valid in the run manifest")
    if not path.is_file():
        return {"status": "invalid", "errors": ["runtime feature snapshot is missing"]}
    if Path(str(descriptor.get("path", ""))).name != path.name:
        errors.append("runtime feature snapshot path does not resolve to the archived table")
    if digest(path) != descriptor.get("sha256"):
        errors.append("runtime feature snapshot hash does not match its run manifest")
    if descriptor.get("source_input_dataset_identifier") != manifest.get("dataset_identifier"):
        errors.append("runtime features are not tied to the hashed run input manifest")
    source_provenance = descriptor.get("source_input_provenance")
    input_rows = manifest.get("inputs", [])
    expected_provenance = {
        str(item.get("path")): {
            "sha256": item.get("sha256"),
            "fetched_at_utc": (item.get("cache_metadata") or {}).get("fetched_at"),
            "source": (item.get("cache_metadata") or {}).get("source"),
        }
        for item in input_rows
    }
    if not isinstance(source_provenance, list) or len(source_provenance) != len(expected_provenance):
        errors.append("runtime feature source provenance is missing or incomplete")
    else:
        for item in source_provenance:
            expected = expected_provenance.get(str(item.get("path")))
            actual = {key: item.get(key) for key in ("sha256", "fetched_at_utc", "source")}
            if expected is None or actual != expected:
                errors.append("runtime feature source provenance differs from hashed input manifest")
                break
    try:
        rows = pd.read_parquet(path)
    except Exception as exc:
        return {"status": "invalid", "errors": [f"cannot read runtime feature snapshot: {exc}"]}
    required = {
        "forecast_record_id", "dunkest_player_id", "canonical_player_id", "nba_game_id",
        "player_key", "feature_match_status", "candidate_key_count", "source_feature_row_count",
    }
    if missing := sorted(required - set(rows.columns)):
        errors.append(f"runtime feature snapshot lacks fields: {missing}")
        return {
            "status": "invalid", "errors": errors,
            "candidate_rows": int(len(rows)), "hgb_transformed_feature_columns": [],
        }
    if manifest_schema >= 2:
        versions = pd.to_numeric(
            rows.get("runtime_feature_schema_version", pd.Series(dtype=float)), errors="coerce"
        )
        if len(versions) != len(rows) or versions.isna().any() or not versions.eq(1).all():
            errors.append("runtime feature rows do not match schema version 1")
    if len(rows) != int(descriptor.get("candidate_rows", -1)):
        errors.append("runtime feature candidate row count differs from its manifest")
    if rows.empty or rows["forecast_record_id"].isna().any() or rows["forecast_record_id"].duplicated().any():
        errors.append("runtime feature record IDs are missing or duplicated")
    statuses = set(rows.get("feature_match_status", pd.Series(dtype=str)).dropna().astype(str))
    if statuses - {"matched", "missing"}:
        errors.append(f"runtime feature identity is ambiguous or has unknown status: {sorted(statuses)}")
    shadow_available = rows.get(
        "minutes_shadow_status", pd.Series("unavailable", index=rows.index)
    ).eq("available")
    model_inputs = [column for column in rows if column.startswith("runtime_feature__hgb_input__")]
    if shadow_available.any() and not model_inputs:
        errors.append("available HGB predictions lack their transformed feature matrix")
    if shadow_available.any() and not rows.loc[shadow_available, "feature_match_status"].eq("matched").all():
        errors.append("available HGB prediction is not linked to a unique runtime feature row")
    if shadow_available.any() and model_inputs:
        matrix = rows.loc[shadow_available, model_inputs].apply(pd.to_numeric, errors="coerce")
        if matrix.isna().any().any() or not np.isfinite(matrix.to_numpy(dtype=float)).all():
            errors.append("transformed HGB feature matrix has missing or non-finite values")
    available_column = "runtime_feature__available_at_utc"
    if available_column in rows:
        available_at = pd.to_datetime(rows[available_column], errors="coerce", utc=True)
        forecast_at = pd.to_datetime(rows.get(
            "forecast_timestamp_utc", pd.Series(pd.NaT, index=rows.index)
        ), errors="coerce", utc=True)
        if available_at.isna().any() or forecast_at.isna().any() or (available_at > forecast_at).any():
            errors.append("runtime feature availability is missing or after the forecast timestamp")
    if forecasts is None:
        forecast_path = run_dir / "player_forecast_snapshot.parquet"
        if forecast_path.is_file():
            try:
                forecasts = pd.read_parquet(forecast_path)
            except Exception:
                forecasts = None
    identity = ["forecast_record_id", "dunkest_player_id", "nba_game_id"]
    if forecasts is not None and set(identity).issubset(forecasts) and set(identity).issubset(rows):
        left = forecasts[identity].sort_values("forecast_record_id").reset_index(drop=True)
        right = rows[identity].sort_values("forecast_record_id").reset_index(drop=True)
        if not left.astype("string").equals(right.astype("string")):
            errors.append("runtime feature rows do not map one-to-one to frozen candidate identities")
    return {
        "status": "valid" if not errors else "invalid", "errors": errors,
        "candidate_rows": int(len(rows)), "hgb_transformed_feature_columns": model_inputs,
    }


def player_forecast_snapshot_validation(run_dir: Path, manifest: dict) -> dict:
    """Require an all-candidate forecast table tied to a sourced exact lock time."""
    import pandas as pd

    manifest_schema = _manifest_schema_version(manifest)
    if manifest_schema is None:
        return {"status": "invalid", "errors": ["run manifest schema version is invalid"]}
    if manifest_schema < 2:
        return {
            "status": "legacy",
            "errors": ["legacy forecast archive has no versioned component snapshot contract"],
        }
    descriptor = manifest.get("player_forecast_snapshot", {})
    path = run_dir / "player_forecast_snapshot.parquet"
    certification = descriptor.get("certification", {})
    errors = []
    if not path.is_file():
        return {"status": "invalid", "errors": ["all-candidate forecast snapshot is missing"]}
    if Path(str(descriptor.get("path", ""))).name != path.name:
        errors.append("forecast snapshot path does not resolve to the archived table")
    if digest(path) != descriptor.get("sha256"):
        errors.append("forecast snapshot hash does not match its run manifest")
    cutoff = utc(descriptor.get("prediction_cutoff_utc"))
    forecasted_at = utc(descriptor.get("forecast_timestamp_utc"))
    run_time = utc(manifest.get("timestamp"))
    source_hash = str(descriptor.get("cutoff_source_sha256", "")).lower()
    if (
        not descriptor.get("cutoff_verified", False)
        or not certification.get("exact_dunkest_cutoff_verified", False)
        or not descriptor.get("cutoff_basis")
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        errors.append("exact Dunkest lock time lacks verified source provenance/hash")
    if cutoff is None or forecasted_at is None or run_time is None:
        errors.append("forecast, lock or run timestamp is missing/invalid")
    elif forecasted_at >= cutoff or run_time >= cutoff:
        errors.append("forecast or completed run is at/after the Dunkest lock cutoff")
    try:
        forecasts = pd.read_parquet(path)
        required = {
            "player_key", "canonical_player_id", "canonical_player_id_source",
            "dunkest_player_id", "forecast_run_id", "forecast_record_id",
            "minutes_hybrid_status", "minutes_shadow_status",
            "expected_min_model_shadow", "team", "opponent", "dunkest_turn",
            "nba_game_id", "dunkest_match_id", "fixture_verified", "role", "lineup_group",
            "status", "cr", "expected_min", "expected_pdk_conditional", "expected_pdk", "p_play",
            "forecast_timestamp_utc", "prediction_cutoff_utc",
            "lineups_availability_observed_at_utc", "injury_availability_observed_at_utc",
            "forecast_model_version",
        }
        missing = sorted(required - set(forecasts.columns))
        if missing:
            errors.append(f"forecast table lacks fields: {missing}")
        if len(forecasts) != int(descriptor.get("candidate_rows", -1)) or forecasts.empty:
            errors.append("candidate forecast row count is empty or differs from its manifest")
        if {"canonical_player_id_source", "canonical_player_id"}.issubset(forecasts.columns):
            stable = forecasts["canonical_player_id_source"].eq("dunkest_player_id")
            supplied = forecasts["dunkest_player_id"].astype("string").str.strip().notna() & forecasts[
                "dunkest_player_id"
            ].astype("string").str.strip().ne("")
            if not stable.all() or not supplied.all():
                errors.append("stable Dunkest player ID is missing for one or more candidates")
        if "forecast_record_id" in forecasts and forecasts["forecast_record_id"].duplicated().any():
            errors.append("forecast record IDs are missing or duplicated")
        if {"canonical_player_id", "nba_game_id"}.issubset(forecasts.columns):
            identity = forecasts["canonical_player_id"].astype("string") + "|" + forecasts[
                "nba_game_id"
            ].astype("string")
            if identity.duplicated().any():
                errors.append("duplicate stable player/game forecast identity")
        evidence_name = Path(str(descriptor.get("cutoff_evidence_path", ""))).name
        evidence_path = run_dir / evidence_name if evidence_name else None
        if (
            descriptor.get("cutoff_status") != "certified"
            or descriptor.get("certification_status") != "certified"
            or descriptor.get("cutoff_kind") != "official_rule_derived"
            or not evidence_path
            or not evidence_path.is_file()
            or digest(evidence_path) != descriptor.get("cutoff_evidence_file_sha256")
        ):
            errors.append("certified cutoff evidence file is missing, altered, or not officially rule-derived")
        else:
            try:
                evidence = load_json(evidence_path)
                payloads = evidence.get("evidence_payloads", {})
                for key, payload_name in (("config", "config"), ("matchday", "matchday")):
                    payload_hash = hashlib.sha256(
                        json.dumps(
                            payloads[payload_name], sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False,
                        ).encode("utf-8")
                    ).hexdigest()
                    if payload_hash != evidence.get("source_payload_sha256", {}).get(key):
                        errors.append(f"official cutoff {key} payload hash mismatch")
                if (
                    evidence.get("status") != "certified"
                    or evidence.get("cutoff_kind") != "official_rule_derived"
                    or evidence.get("cutoff_semantics") != "official_rule_derived:first_match_started_at_minus_1_minute"
                    or "https://www.dunkest.com/it/notizie/fantabasket/8774/calendario-dunkest-cosa-sono-giornata-turni" not in evidence.get("source_urls", [])
                    or "https://www.dunkest.com/it/nba/notizie/fantabasket/19903/check-list-giornata-cosa-fare-quando" not in evidence.get("source_urls", [])
                    or int(evidence.get("gameweek", -1)) != int(manifest.get("configuration", {}).get("target_gameweek", manifest.get("target_gameweek", -2)))
                    or evidence.get("evidence_sha256") != descriptor.get("cutoff_source_sha256")
                ):
                    errors.append("official cutoff evidence identity does not match the run descriptor")
                recomputed_evidence_hash = hashlib.sha256(
                    json.dumps({
                        "config_payload_sha256": evidence.get("source_payload_sha256", {}).get("config"),
                        "matchday_payload_sha256": evidence.get("source_payload_sha256", {}).get("matchday"),
                        "turn_rule_url": "https://www.dunkest.com/it/notizie/fantabasket/8774/calendario-dunkest-cosa-sono-giornata-turni",
                        "lock_rule_url": "https://www.dunkest.com/it/nba/notizie/fantabasket/19903/check-list-giornata-cosa-fare-quando",
                        "gameweek": int(evidence.get("gameweek", -1)),
                        "turn_cutoffs_utc": evidence.get("turn_cutoffs_utc", {}),
                        "fixture_links": sorted(
                            evidence.get("fixture_links", []),
                            key=lambda item: (item["dunkest_turn"], item["nba_game_id"]),
                        ),
                    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                if recomputed_evidence_hash != evidence.get("evidence_sha256"):
                    errors.append("official cutoff evidence resolution hash mismatch")
                acquired_values = evidence.get("acquired_at_utc", {})
                acquired = [utc(acquired_values.get(key)) for key in ("config", "matchday")]
                turn_cutoffs = {
                    str(key): utc(value)
                    for key, value in evidence.get("turn_cutoffs_utc", {}).items()
                }
                if (
                    any(value is None for value in acquired)
                    or any(value is None for value in turn_cutoffs.values())
                    or not turn_cutoffs
                    or max(value for value in acquired if value is not None) > forecasted_at
                    or min(value for value in turn_cutoffs.values() if value is not None) != cutoff
                ):
                    errors.append("official cutoff evidence has missing, late, or inconsistent timestamps")
                if not missing:
                    if "dunkest_turn_cutoff_utc" not in forecasts:
                        errors.append("candidate forecast lacks its turn-specific cutoff")
                    else:
                        row_turns = pd.to_numeric(forecasts["dunkest_turn"], errors="coerce")
                        row_cutoffs = pd.to_datetime(forecasts["dunkest_turn_cutoff_utc"], errors="coerce", utc=True)
                        expected_turn_cutoffs = row_turns.map(
                            lambda value: turn_cutoffs.get(str(int(value))) if pd.notna(value) else None
                        )
                        expected_turn_cutoffs = pd.to_datetime(expected_turn_cutoffs, errors="coerce", utc=True)
                        if row_cutoffs.isna().any() or not row_cutoffs.eq(expected_turn_cutoffs).all():
                            errors.append("candidate turn cutoff differs from the official evidence")
                        forecast_rows = pd.to_datetime(forecasts["forecast_timestamp_utc"], errors="coerce", utc=True)
                        if forecast_rows.isna().any() or (forecast_rows >= row_cutoffs).any():
                            errors.append("candidate forecast timestamp is at/after its turn cutoff")
                    links = evidence.get("fixture_links", [])
                    links_by_game = {str(link.get("nba_game_id")): link for link in links}
                    if len(links_by_game) != len(links):
                        errors.append("official cutoff evidence has duplicate NBA fixture links")
                    else:
                        for _, row in forecasts.iterrows():
                            link = links_by_game.get(str(row.get("nba_game_id", "")))
                            if not link:
                                errors.append("candidate NBA fixture is absent from cutoff evidence")
                                break
                            team = str(row.get("team", "")).strip().upper()
                            opponent = str(row.get("opponent", "")).strip().upper()
                            sides = {str(link.get("home_team", "")).upper(), str(link.get("away_team", "")).upper()}
                            if (
                                str(row.get("dunkest_match_id", "")).strip() != str(link.get("dunkest_match_id", "")).strip()
                                or int(pd.to_numeric(row.get("dunkest_turn"), errors="coerce")) != int(link.get("dunkest_turn", -1))
                                or team not in sides or opponent not in sides or team == opponent
                            ):
                                errors.append("candidate team/opponent/turn/match identity differs from cutoff evidence")
                                break
            except Exception as exc:
                errors.append(f"cannot validate official cutoff evidence: {exc}")
        if not missing:
            if not forecasts["fixture_verified"].fillna(False).astype(bool).all():
                errors.append("one or more candidate fixture mappings are unverified")
            if forecasts[["player_key", "team", "opponent", "dunkest_turn", "nba_game_id"]].isna().any().any():
                errors.append("candidate fixture identity fields contain missing values")
            row_forecasts = pd.to_datetime(forecasts["forecast_timestamp_utc"], errors="coerce", utc=True)
            row_cutoffs = pd.to_datetime(forecasts["prediction_cutoff_utc"], errors="coerce", utc=True)
            if row_forecasts.isna().any() or row_cutoffs.isna().any() or (row_forecasts >= row_cutoffs).any():
                errors.append("candidate forecast timestamp is missing or at/after cutoff")
            for timestamp_column in (
                "lineups_availability_observed_at_utc",
                "injury_availability_observed_at_utc",
            ):
                observed = pd.to_datetime(forecasts[timestamp_column], errors="coerce", utc=True)
                if observed.isna().any() or (observed > row_forecasts).any():
                    errors.append(f"{timestamp_column} is missing or after the forecast")
            if forecasts.duplicated(["player_key", "nba_game_id"]).any():
                errors.append("candidate player-fixture keys are duplicated")
    except Exception as exc:
        errors.append(f"cannot read candidate forecast snapshot: {exc}")
    runtime_validation = runtime_feature_snapshot_validation(
        run_dir, manifest, forecasts if "forecasts" in locals() else None
    )
    if runtime_validation["status"] != "valid":
        errors.extend(runtime_validation["errors"])
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "runtime_feature_snapshot_validation": runtime_validation,
    }


def versioned_forecast_snapshot_validation(run_dir: Path, manifest: dict) -> dict:
    """Validate versioned player, runtime, shadow and full coach snapshots.

    This checks archive structure and temporal consistency. It does not certify
    the official lock source or prove forecast quality; those are separate gates.
    """
    import pandas as pd

    schema_version = _manifest_schema_version(manifest)
    if schema_version is None:
        return {"status": "unverifiable", "errors": ["run manifest schema version is invalid"], "components": {}}
    if schema_version < 2:
        return {
            "status": "legacy",
            "errors": ["legacy archive predates the versioned forecast snapshot contract"],
            "components": {},
        }

    errors: list[str] = []
    components: dict[str, dict] = {}
    tables: dict[str, pd.DataFrame] = {}
    snapshot_schemas = manifest.get("snapshot_schemas", {})
    snapshot_specs = {
        "player_forecast_snapshot": ("player_forecast", "player_forecast_snapshot.parquet", 1, "forecast_schema_version"),
        "runtime_feature_snapshot": ("runtime_features", "runtime_feature_snapshot.parquet", 1, "runtime_feature_schema_version"),
        "shadow_forecast_snapshot": ("shadow_forecast", "shadow_forecast_snapshot.parquet", 1, "shadow_forecast_schema_version"),
        "coach_forecast_snapshot": ("coach_forecast", "coach_forecast_snapshot.parquet", 1, "coach_forecast_schema_version"),
    }
    hash_or_schema_errors = False
    missing_components = False
    ambiguous_mapping = False

    for descriptor_key, (schema_key, filename, expected_version, row_version_column) in snapshot_specs.items():
        descriptor = manifest.get(descriptor_key)
        if not isinstance(descriptor, dict):
            components[descriptor_key] = {"status": "missing", "errors": ["snapshot descriptor is missing"]}
            errors.append(f"{descriptor_key}: snapshot descriptor is missing")
            missing_components = True
            continue
        path = run_dir / filename
        component_errors: list[str] = []
        if snapshot_schemas.get(schema_key) != expected_version or descriptor.get("schema_version") != expected_version:
            component_errors.append("manifest snapshot schema version is missing or unsupported")
            hash_or_schema_errors = True
        if Path(str(descriptor.get("path", ""))).name != filename:
            component_errors.append("snapshot path does not resolve to its versioned table")
            hash_or_schema_errors = True
        if not path.is_file():
            component_errors.append("snapshot file is missing")
            missing_components = True
            components[descriptor_key] = {"status": "missing", "errors": component_errors}
            errors.extend(f"{descriptor_key}: {error}" for error in component_errors)
            continue
        if digest(path) != descriptor.get("sha256"):
            component_errors.append("snapshot hash differs from its run manifest")
            hash_or_schema_errors = True
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            component_errors.append(f"snapshot cannot be read: {exc}")
            hash_or_schema_errors = True
            components[descriptor_key] = {"status": "invalid", "errors": component_errors}
            errors.extend(f"{descriptor_key}: {error}" for error in component_errors)
            continue
        tables[descriptor_key] = frame
        expected_rows = descriptor.get("candidate_rows", descriptor.get("rows"))
        if expected_rows is not None:
            try:
                row_count_matches = int(expected_rows) == len(frame)
            except (TypeError, ValueError):
                row_count_matches = False
            if not row_count_matches:
                component_errors.append("snapshot row count is invalid or differs from manifest")
                hash_or_schema_errors = True
        declared_columns = descriptor.get("columns")
        if isinstance(declared_columns, list) and not set(declared_columns).issubset(frame.columns):
            component_errors.append("snapshot is missing columns declared in its manifest")
            hash_or_schema_errors = True
        if row_version_column not in frame:
            component_errors.append(f"snapshot rows lack {row_version_column}")
            hash_or_schema_errors = True
        else:
            versions = pd.to_numeric(frame[row_version_column], errors="coerce")
            if versions.isna().any() or not versions.eq(expected_version).all():
                component_errors.append("snapshot row schema versions are inconsistent")
                hash_or_schema_errors = True
        allowed_component_statuses = {"valid", "unavailable"} if schema_key == "shadow_forecast" else {"valid"}
        if descriptor.get("status") not in allowed_component_statuses:
            component_errors.append(f"manifest marks snapshot status as {descriptor.get('status')!r}")
            missing_components = True
        components[descriptor_key] = {
            "status": "valid" if not component_errors else "invalid",
            "rows": int(len(frame)), "errors": component_errors,
        }
        errors.extend(f"{descriptor_key}: {error}" for error in component_errors)

    players = tables.get("player_forecast_snapshot")
    runtime = tables.get("runtime_feature_snapshot")
    shadow = tables.get("shadow_forecast_snapshot")
    coaches = tables.get("coach_forecast_snapshot")
    required_player = {
        "forecast_run_id", "forecast_record_id", "forecast_schema_version", "player_key",
        "dunkest_player_id", "canonical_player_id", "canonical_player_id_source",
        "nba_game_id", "dunkest_turn", "forecast_timestamp_utc", "prediction_cutoff_utc",
        "forecast_model_version", "forecast_code_version", "forecast_configuration_sha256",
        "forecast_input_dataset_identifier", "forecast_source_fingerprint_sha256",
        "expected_min", "expected_min_model_shadow", "pdk_rate_for_projection", "p_play",
        "ensemble_pdk", "prior_pdk", "implied_min", "has_history", "n_games",
        "historical_rf_pdk", "historical_rf_blend_weight", "component_minutes_pdk",
        "component_ensemble_pdk", "component_prior_pdk", "projection_weight_minutes",
        "projection_weight_ensemble", "projection_weight_prior", "expected_pdk_conditional",
        "expected_pdk",
    }
    if players is not None:
        missing = sorted(required_player - set(players.columns))
        if missing:
            errors.append(f"player forecast snapshot lacks PDK replay fields: {missing}")
            missing_components = True
        if players.empty or players.get("forecast_record_id", pd.Series(dtype=str)).isna().any() or players.get(
            "forecast_record_id", pd.Series(dtype=str)
        ).duplicated().any():
            errors.append("player forecast record IDs are empty or duplicated")
            hash_or_schema_errors = True
        if "forecast_run_id" in players and not players["forecast_run_id"].astype(str).eq(
            str(manifest.get("run_id", ""))
        ).all():
            errors.append("player forecast rows reference a different run ID")
            hash_or_schema_errors = True
        if {"canonical_player_id", "nba_game_id"}.issubset(players.columns):
            identity = players["canonical_player_id"].astype("string") + "|" + players["nba_game_id"].astype("string")
            if identity.isna().any() or identity.duplicated().any():
                errors.append("player/game forecast identities are missing or duplicated")
                hash_or_schema_errors = True
        if {"dunkest_player_id", "canonical_player_id_source"}.issubset(players.columns):
            stable_id = players["dunkest_player_id"].astype("string").str.strip()
            if stable_id.isna().any() or stable_id.eq("").any() or not players[
                "canonical_player_id_source"
            ].eq("dunkest_player_id").all():
                errors.append("one or more player forecasts lack a stable Dunkest player ID")
                missing_components = True
        for column in ("forecast_configuration_sha256", "forecast_input_dataset_identifier", "forecast_source_fingerprint_sha256"):
            if column in players:
                if column == "forecast_configuration_sha256":
                    expected_value = manifest.get("config_sha256")
                elif column == "forecast_input_dataset_identifier":
                    expected_value = manifest.get("dataset_identifier")
                else:
                    expected_value = manifest.get("source_fingerprint", {}).get("sha256")
                if expected_value is None or not players[column].astype("string").eq(str(expected_value)).all():
                    errors.append(f"player forecast {column} differs from manifest provenance")
                    hash_or_schema_errors = True

    if runtime is not None and players is not None:
        runtime_result = runtime_feature_snapshot_validation(run_dir, manifest, players)
        components["runtime_feature_snapshot"]["validation"] = runtime_result
        if runtime_result.get("status") != "valid":
            errors.extend(f"runtime_feature_snapshot: {item}" for item in runtime_result.get("errors", []))
            if any("ambiguous" in str(item).casefold() for item in runtime_result.get("errors", [])):
                ambiguous_mapping = True
            else:
                missing_components |= any("missing" in str(item).casefold() or "lacks fields" in str(item).casefold()
                                          for item in runtime_result.get("errors", []))
                hash_or_schema_errors |= not missing_components
        statuses = set(runtime.get("feature_match_status", pd.Series(dtype=str)).dropna().astype(str))
        if statuses.intersection({"ambiguous_candidate_identity", "ambiguous_feature_identity"}):
            ambiguous_mapping = True
            errors.append("runtime feature snapshot contains ambiguous candidate/feature mappings")
        if "missing" in statuses:
            missing_rows = runtime.loc[
                runtime["feature_match_status"].astype(str).eq("missing")
            ]
            documented_fallback = pd.Series(False, index=missing_rows.index)
            if (
                not missing_rows.empty
                and {"candidate_key_count", "source_feature_row_count", "minutes_shadow_status"}.issubset(runtime.columns)
                and {"forecast_record_id", "history_source", "expected_min_model_shadow"}.issubset(players.columns)
            ):
                player_index = players.set_index("forecast_record_id")
                history_source = missing_rows["forecast_record_id"].map(player_index["history_source"])
                player_shadow = missing_rows["forecast_record_id"].map(
                    player_index["expected_min_model_shadow"]
                )
                documented_fallback = (
                    pd.to_numeric(missing_rows["candidate_key_count"], errors="coerce").eq(1)
                    & pd.to_numeric(missing_rows["source_feature_row_count"], errors="coerce").eq(0)
                    & missing_rows["minutes_shadow_status"].astype(str).eq("unavailable")
                    & history_source.astype(str).eq("history_feature_row_missing")
                    & pd.to_numeric(player_shadow, errors="coerce").isna()
                )
            if missing_rows.empty or not documented_fallback.all():
                missing_components = True
                errors.append(
                    "runtime feature snapshot has unmatched candidates without an explicit "
                    "no-history fallback and unavailable shadow forecast"
                )
        if "forecast_run_id" in runtime and not runtime["forecast_run_id"].astype(str).eq(
            str(manifest.get("run_id", ""))
        ).all():
            errors.append("runtime feature rows reference a different run ID")
            hash_or_schema_errors = True

    player_ids = set(players["forecast_record_id"].astype(str)) if players is not None and "forecast_record_id" in players else set()
    if shadow is not None:
        descriptor = manifest.get("shadow_forecast_snapshot", {})
        if descriptor.get("optimizer_input") is not False:
            errors.append("shadow forecast snapshot is not explicitly excluded from optimizer inputs")
            hash_or_schema_errors = True
        forbidden_shadow_columns = {
            "expected_pdk", "expected_pdk_conditional", "expected_pdk_before_play_probability",
            "component_minutes_pdk", "component_ensemble_pdk", "component_prior_pdk",
        }
        if forbidden_shadow_columns.intersection(shadow.columns):
            errors.append("shadow forecast snapshot contains operational PDK prediction fields")
            hash_or_schema_errors = True
        shadow_ids = set(shadow.get("forecast_record_id", pd.Series(dtype=str)).astype(str))
        if shadow.empty or shadow.get("forecast_record_id", pd.Series(dtype=str)).isna().any() or shadow.get(
            "forecast_record_id", pd.Series(dtype=str)
        ).duplicated().any():
            errors.append("shadow forecast record IDs are empty or duplicated")
            hash_or_schema_errors = True
        if shadow_ids != player_ids:
            errors.append("shadow forecast IDs do not match player forecast IDs")
            hash_or_schema_errors = True
        if "forecast_run_id" in shadow and not shadow["forecast_run_id"].astype(str).eq(
            str(manifest.get("run_id", ""))
        ).all():
            errors.append("shadow forecast rows reference a different run ID")
            hash_or_schema_errors = True
        if {"expected_min_model_shadow", "minutes_shadow_status"}.issubset(shadow.columns):
            shadow_values = pd.to_numeric(shadow["expected_min_model_shadow"], errors="coerce")
            available = shadow["minutes_shadow_status"].astype(str).eq("available")
            unavailable = shadow["minutes_shadow_status"].astype(str).eq("unavailable")
            if not (available | unavailable).all() or available.ne(shadow_values.notna()).any():
                errors.append("shadow availability status does not match its minute forecast values")
                hash_or_schema_errors = True
            if players is not None and "forecast_record_id" in players:
                expected = players.set_index("forecast_record_id")["expected_min_model_shadow"]
                actual = shadow.set_index("forecast_record_id")["expected_min_model_shadow"]
                aligned = pd.to_numeric(actual.reindex(expected.index), errors="coerce")
                source = pd.to_numeric(expected, errors="coerce")
                if not aligned.equals(source):
                    errors.append("shadow minute values do not match the candidate forecast record IDs")
                    hash_or_schema_errors = True

    if coaches is not None:
        required_coaches = {
            "forecast_run_id", "forecast_record_id", "coach_key", "coach", "team", "nba_game_id",
            "dunkest_turn", "forecast_timestamp_utc", "prediction_cutoff_utc", "expected_coach_pdk",
            "coach_cr", "coach_forecast_schema_version", "forecast_model_version",
            "forecast_code_version", "forecast_configuration_sha256", "forecast_input_dataset_identifier",
            "forecast_source_fingerprint_sha256",
        }
        missing = sorted(required_coaches - set(coaches.columns))
        if missing:
            errors.append(f"coach forecast snapshot is incomplete; missing fields: {missing}")
            missing_components = True
        if coaches.empty:
            errors.append("coach forecast snapshot contains no forecast candidates")
            missing_components = True
        if "forecast_record_id" in coaches and (
            coaches["forecast_record_id"].isna().any() or coaches["forecast_record_id"].duplicated().any()
        ):
            errors.append("coach forecast record IDs are missing or duplicated")
            hash_or_schema_errors = True
        if "forecast_run_id" in coaches and not coaches["forecast_run_id"].astype(str).eq(
            str(manifest.get("run_id", ""))
        ).all():
            errors.append("coach forecast rows reference a different run ID")
            hash_or_schema_errors = True
        for column in ("forecast_configuration_sha256", "forecast_input_dataset_identifier", "forecast_source_fingerprint_sha256"):
            if column in coaches:
                if column == "forecast_configuration_sha256":
                    expected_value = manifest.get("config_sha256")
                elif column == "forecast_input_dataset_identifier":
                    expected_value = manifest.get("dataset_identifier")
                else:
                    expected_value = manifest.get("source_fingerprint", {}).get("sha256")
                if expected_value is None or not coaches[column].astype("string").eq(str(expected_value)).all():
                    errors.append(f"coach forecast {column} differs from manifest provenance")
                    hash_or_schema_errors = True

    forecast_descriptor = manifest.get("player_forecast_snapshot", {})
    forecast_at = utc(forecast_descriptor.get("forecast_timestamp_utc"))
    cutoff = utc(forecast_descriptor.get("prediction_cutoff_utc"))
    run_at = utc(manifest.get("timestamp"))
    if forecast_at is None or cutoff is None or run_at is None:
        errors.append("forecast, cutoff or run timestamp is missing/invalid")
        hash_or_schema_errors = True
    elif forecast_at >= cutoff or run_at >= cutoff:
        errors.append("forecast or run timestamp is at/after the applicable cutoff")
        hash_or_schema_errors = True
    for descriptor_key, frame in (
        ("player_forecast_snapshot", players),
        ("runtime_feature_snapshot", runtime),
        ("shadow_forecast_snapshot", shadow),
        ("coach_forecast_snapshot", coaches),
    ):
        if frame is None or not {"forecast_timestamp_utc", "prediction_cutoff_utc"}.issubset(frame.columns):
            continue
        row_forecast = pd.to_datetime(frame["forecast_timestamp_utc"], errors="coerce", utc=True)
        row_cutoff = pd.to_datetime(frame["prediction_cutoff_utc"], errors="coerce", utc=True)
        if row_forecast.isna().any() or row_cutoff.isna().any() or (row_forecast >= row_cutoff).any():
            errors.append(f"{descriptor_key} has missing timestamps or forecasts at/after cutoff")
            hash_or_schema_errors = True
        if forecast_at is not None and not row_forecast.eq(pd.Timestamp(forecast_at)).all():
            errors.append(f"{descriptor_key} forecast timestamps differ from run forecast timestamp")
            hash_or_schema_errors = True
        if cutoff is not None and not row_cutoff.eq(pd.Timestamp(cutoff)).all():
            errors.append(f"{descriptor_key} cutoff timestamps differ from manifest cutoff")
            hash_or_schema_errors = True

    for descriptor_key, frame in (("player_forecast_snapshot", players), ("coach_forecast_snapshot", coaches)):
        if frame is None or not {"forecast_model_version", "forecast_code_version"}.issubset(frame.columns):
            continue
        model_versions = frame["forecast_model_version"].astype("string")
        code_versions = frame["forecast_code_version"].astype("string")
        if model_versions.isna().any() or model_versions.str.strip().eq("").any() or not model_versions.eq(code_versions).all():
            errors.append(f"{descriptor_key} model/code provenance is missing or inconsistent")
            hash_or_schema_errors = True

    if players is not None and forecast_at is not None:
        for column in (
            "availability_observed_at_utc",
            "lineups_availability_observed_at_utc",
            "injury_availability_observed_at_utc",
        ):
            if column not in players:
                continue
            raw = players[column]
            observed = pd.to_datetime(raw, errors="coerce", utc=True)
            invalid = raw.notna() & observed.isna()
            late = observed.notna() & observed.gt(pd.Timestamp(forecast_at))
            if invalid.any() or late.any():
                errors.append(f"player forecast {column} is invalid or later than the forecast")
                hash_or_schema_errors = True

    if manifest.get("archive_status") != "complete" or manifest.get("persistence_errors"):
        errors.append("run manifest marks forecast snapshots incomplete or records persistence errors")
        missing_components = True

    if ambiguous_mapping:
        status = "mapping_ambiguous"
    elif missing_components:
        status = "incomplete"
    elif hash_or_schema_errors or errors:
        status = "unverifiable"
    else:
        status = "complete"
    return {"status": status, "errors": errors, "components": components}


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
    market_name = f"dunkest_players_{season}_gw{int(gw)}.parquet"
    market_evidence = (
        manifest.get("required_pre_match_inputs", {}).get("dunkest_market_snapshot", {})
    )
    explicitly_missing_market = bool(
        market_name in missing_snapshots
        and isinstance(market_evidence, dict)
        and market_evidence.get("status") == "missing"
        and market_evidence.get("path") == market_name
        and not market_evidence.get("sha256")
    )
    unaccounted_missing = [
        name for name in missing_snapshots
        if name != market_name or not explicitly_missing_market
    ]
    if unaccounted_missing:
        raise ValueError(f"Required pre-match snapshots missing: {unaccounted_missing}")
    content_validation = snapshot_content_validation(run_dir, manifest)
    forecast_validation = player_forecast_snapshot_validation(run_dir, manifest)
    snapshot_bundle_validation = versioned_forecast_snapshot_validation(run_dir, manifest)
    fixture_validation = fixture_mapping_validation(run_dir, manifest, max_hours)
    eligible = (
        all(x["status"] == "fresh" for x in snap_status)
        and all(x["status"] == "valid" for x in content_validation)
        and forecast_validation["status"] == "valid"
        and snapshot_bundle_validation["status"] == "complete"
        and fixture_validation["status"] == "verified"
        and bool(manifest.get("player_forecast_snapshot", {}).get("certification", {}).get("pre_lock_eligible", False))
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
                "schema_version": 2, "run_id": run_id,
                "archived_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_run_dir": str(run_dir),
                "source_manifest_sha256": digest(run_dir / "manifest.json"),
                "max_snapshot_age_hours": max_hours,
                "snapshot_freshness": snap_status,
                "snapshot_content_validation": content_validation,
                "player_forecast_snapshot_validation": forecast_validation,
                "versioned_forecast_snapshot_validation": snapshot_bundle_validation,
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
        "schema_version": int(archive_meta.get("schema_version", 1)),
        "run_id": run_id, "season_id": season, "gameweek": int(gw),
        "run_timestamp": manifest.get("timestamp"),
        "archive_path": str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest),
        "archive_manifest_sha256": digest(dest / "archive_manifest.json"),
        "pre_lock_eligible": bool(archive_meta.get("pre_lock_eligible")),
        "eligibility_status": archive_meta.get("eligibility_status"),
        "snapshot_freshness": archive_meta.get("snapshot_freshness", []),
        "predictions_sha256": digest(dest / "predictions.parquet"),
        "lineups_sha256": digest(dest / "lineups.parquet"),
    }
    if record["schema_version"] >= 2:
        for filename, field in (
            ("player_forecast_snapshot.parquet", "player_forecast_snapshot_sha256"),
            ("runtime_feature_snapshot.parquet", "runtime_feature_snapshot_sha256"),
            ("shadow_forecast_snapshot.parquet", "shadow_forecast_snapshot_sha256"),
            ("coach_forecast_snapshot.parquet", "coach_forecast_snapshot_sha256"),
        ):
            path = dest / filename
            record[field] = digest(path) if path.is_file() else None
        record["versioned_forecast_snapshot_validation"] = archive_meta.get(
            "versioned_forecast_snapshot_validation",
            {"status": "unverifiable", "errors": ["archive has no snapshot validation record"]},
        )
    elif registry_path.is_file():
        # Preserve the first-generation registry shape for already archived
        # bundles. That schema optionally recorded player/runtime snapshot hashes.
        previous_registry = load_json(registry_path)
        for filename, field in (
            ("player_forecast_snapshot.parquet", "player_forecast_snapshot_sha256"),
            ("runtime_feature_snapshot.parquet", "runtime_feature_snapshot_sha256"),
        ):
            if field in previous_registry:
                path = dest / filename
                record[field] = digest(path) if path.is_file() else None
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
            "forecast_snapshot_validation": archive_meta.get(
                "versioned_forecast_snapshot_validation",
                {"status": "legacy", "errors": ["no versioned snapshot validation was stored"]},
            ),
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
