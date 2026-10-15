from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.names import player_key
from dunkest.rules.roster import player_contribution_multiplier
from dunkest.backtest.timing import safe_postgame_retrieval_cutoff


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Manifest root is not an object: {path}")
    return value


def score_column(frame: pd.DataFrame, candidates: tuple[str, ...], label: str) -> str:
    for name in candidates:
        if name in frame.columns:
            return name
    raise ValueError(f"{label} missing score column; accepted: {candidates}")


def id_column(frame: pd.DataFrame, candidates: tuple[str, ...], label: str) -> str:
    for name in candidates:
        if name in frame.columns:
            return name
    raise ValueError(f"{label} missing identity/fixture column; accepted: {candidates}")


def canonical_actuals(frame: pd.DataFrame, entity: str, score_names: tuple[str, ...]) -> tuple[pd.DataFrame, dict]:
    name_names = ("player_name", "dunkest_player_name", "name") if entity == "player" else ("coach", "coach_name", "name")
    name_col = id_column(frame, name_names, f"{entity} results")
    fixture_col = id_column(frame, ("nba_game_id", "game_id", "gameId", "GAME_ID", "Game_ID"), f"{entity} results")
    score_col = score_column(frame, score_names, f"{entity} results")
    out = frame[[name_col, fixture_col, score_col]].copy()
    out.columns = [entity, "nba_game_id", "actual_score"]
    out[entity] = out[entity].astype(str).str.strip()
    out["_key"] = out[entity].map(player_key)
    out["nba_game_id"] = out["nba_game_id"].astype(str).str.strip()
    out["actual_score"] = pd.to_numeric(out["actual_score"], errors="coerce")
    out = out.loc[out["_key"].ne("") & ~out["nba_game_id"].isin({"", "nan", "None", "<NA>"}) & np.isfinite(out["actual_score"])].copy()
    dup = out.duplicated(["_key", "nba_game_id"], keep=False)
    if dup.any():
        conflicts = out.loc[dup].groupby(["_key", "nba_game_id"])["actual_score"].nunique()
        conflicts = conflicts[conflicts > 1]
        if not conflicts.empty:
            raise ValueError(f"Conflicting {entity} scores for the same fixture key: {list(conflicts.index[:5])}")
        out = out.drop_duplicates(["_key", "nba_game_id"], keep="last")
    return out, {"input_rows": int(len(frame)), "valid_rows": int(len(out)), "entities": int(out["_key"].nunique()), "fixtures": int(out["nba_game_id"].nunique()), "identity_column": name_col, "fixture_column": fixture_col, "score_column": score_col}


def latest_run(data: Path, season_id: str, gameweek: int, run_id: str | None) -> Path:
    if run_id:
        candidate = data / "predictions" / run_id
        if not (candidate / "manifest.json").is_file():
            raise FileNotFoundError(f"Prediction manifest not found: {candidate / 'manifest.json'}")
        return candidate
    matches = []
    for path in (data / "predictions").glob("*/manifest.json"):
        try:
            m = read_json(path)
            c = m.get("configuration", {})
            if str(c.get("season_id", m.get("season_id", ""))) == str(season_id) and int(c.get("target_gameweek", m.get("target_gameweek", -1))) == gameweek:
                matches.append((str(m.get("timestamp", "")), path.parent))
        except Exception:
            continue
    if not matches:
        raise FileNotFoundError(f"No prediction run for season_id={season_id}, GW{gameweek}")
    return sorted(matches, key=lambda item: item[0])[-1][1]


def resolve_run_dir(
    data: Path,
    season_id: str,
    gameweek: int,
    run_id: str | None = None,
    run_dir: str | Path | None = None,
) -> Path:
    """Resolve either a standard run ID or an explicit immutable workspace run."""
    if not run_dir:
        return latest_run(data, season_id, gameweek, run_id)
    candidate = Path(run_dir).expanduser().resolve()
    manifest_path = candidate / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Prediction manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    resolved_id = str(manifest.get("run_id", candidate.name))
    if run_id and run_id != resolved_id:
        raise ValueError(f"--run-id {run_id!r} does not match manifest run_id {resolved_id!r}.")
    config = manifest.get("configuration", {})
    resolved_season = str(config.get("season_id", manifest.get("season_id", "")))
    resolved_gameweek = int(config.get("target_gameweek", manifest.get("target_gameweek", -1)))
    if resolved_season != str(season_id) or resolved_gameweek != int(gameweek):
        raise ValueError(
            f"Explicit run is season_id={resolved_season}, GW{resolved_gameweek}; "
            f"requested season_id={season_id}, GW{gameweek}."
        )
    return candidate


def latest_results(data: Path, season_id: str, gameweek: int, explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not (path / "manifest.json").is_file():
            raise FileNotFoundError(f"Post-match manifest not found: {path / 'manifest.json'}")
        return path
    base = data / "archive" / str(season_id) / f"gw{gameweek}"
    matches = []
    if base.is_dir():
        for path in base.glob("post_match_*/manifest.json"):
            try:
                m = read_json(path)
                if str(m.get("season_id")) == str(season_id) and int(m.get("dunkest_gameweek", -1)) == gameweek:
                    matches.append((str(m.get("retrieved_at_utc", "")), path.parent))
            except Exception:
                continue
    return sorted(matches, key=lambda item: item[0])[-1][1] if matches else None


def validate_run(run_dir: Path, manifest: dict) -> tuple[pd.DataFrame, dict]:
    config = manifest.get("configuration", {})
    season_id = str(config.get("season_id", manifest.get("season_id", "")))
    gw = int(config.get("target_gameweek", manifest.get("target_gameweek", -1)))
    run_time = pd.to_datetime(manifest.get("timestamp"), utc=True, errors="coerce")
    if pd.isna(run_time):
        raise ValueError("Prediction run has no valid UTC timestamp.")
    snap = manifest.get("pre_match_snapshot", {})
    files = snap.get("files", [])
    if not files:
        raise ValueError("Prediction run contains no archived pre-match inputs.")
    for entry in files:
        path = run_dir / "pre_match_snapshot" / str(entry.get("path", ""))
        if not path.is_file():
            raise ValueError(f"Pre-match snapshot missing: {entry.get('path')}")
        if sha256(path) != entry.get("sha256"):
            raise ValueError(f"Pre-match snapshot hash mismatch: {entry.get('path')}")
    mappings = [entry for entry in files if str(entry.get("path", "")).startswith("dunkest_fixture_mapping_")]
    if not mappings:
        raise ValueError("No archived fixture mapping in this prediction run.")
    mapping = pd.read_parquet(run_dir / "pre_match_snapshot" / mappings[0]["path"])
    required = {"nba_game_id", "game_datetime_utc", "dunkest_gameweek", "mapping_verified"}
    if not required.issubset(mapping.columns):
        raise ValueError(f"Fixture mapping missing columns: {sorted(required - set(mapping.columns))}")
    mapping = mapping.loc[pd.to_numeric(mapping["dunkest_gameweek"], errors="coerce").eq(gw)].copy()
    if mapping.empty:
        raise ValueError(f"No fixture mapping rows found for GW{gw}.")
    if not mapping["mapping_verified"].fillna(False).astype(bool).all():
        raise ValueError("Fixture mapping includes unverified fixtures.")
    kickoffs = pd.to_datetime(mapping["game_datetime_utc"], utc=True, errors="coerce")
    if kickoffs.isna().any() or run_time >= kickoffs.min():
        raise ValueError("Prediction run timestamp must precede every mapped fixture kickoff.")
    if {"source_retrieved_at_utc", "raw_payload_sha256"}.issubset(mapping.columns):
        retrieved = pd.to_datetime(mapping["source_retrieved_at_utc"], utc=True, errors="coerce")
        hashes = mapping["raw_payload_sha256"].fillna("").astype(str).str.strip()
        if retrieved.isna().any() or (retrieved > kickoffs).any() or hashes.eq("").any():
            raise ValueError("Fixture mapping has invalid retrieval timestamps or payload hashes.")

    # A run timestamp alone does not prove that its cached inputs were acquired
    # before tip-off. Require timestamped sidecars for all decision-critical
    # market snapshots, and retain failures as explicit readiness diagnostics.
    required_inputs = {
        "player_credits": lambda name: name.startswith("player_credits_"),
        "coach_market": lambda name: name.startswith("coach_market_"),
        "injuries": lambda name: name.startswith("injuries_"),
        "current_lineups_market": lambda name: name == "current_lineups_market.csv",
        "lineups_availability": lambda name: name == "lineups_availability.csv",
    }
    snapshot_names = {str(entry.get("path", "")) for entry in files}
    input_capture_checks = {}
    for label, matches in required_inputs.items():
        data_names = sorted(name for name in snapshot_names if not name.endswith(".meta.json") and matches(name))
        if not data_names:
            input_capture_checks[label] = {"present": False, "metadata_present": False, "timestamp_valid": False, "reason": "required snapshot missing"}
            continue
        per_file = []
        for data_name in data_names:
            meta_name = data_name + ".meta.json"
            meta_entry = next((entry for entry in files if str(entry.get("path", "")) == meta_name), None)
            if meta_entry is None:
                per_file.append({"path": data_name, "metadata_present": False, "timestamp_valid": False, "reason": "timestamp sidecar missing"})
                continue
            meta_path = run_dir / "pre_match_snapshot" / meta_name
            try:
                meta = read_json(meta_path)
            except (OSError, ValueError, json.JSONDecodeError):
                per_file.append({"path": data_name, "metadata_present": False, "timestamp_valid": False, "reason": "timestamp sidecar invalid JSON"})
                continue
            capture_time = pd.to_datetime(meta.get("fetched_at") or meta.get("captured_at_utc") or meta.get("retrieved_at_utc"), utc=True, errors="coerce")
            valid_time = bool(pd.notna(capture_time) and capture_time < kickoffs.min())
            row_timestamp_check = None
            if data_name == "lineups_availability.csv":
                availability_path = run_dir / "pre_match_snapshot" / data_name
                try:
                    availability = pd.read_csv(availability_path)
                    turn_value = config.get("target_dunkest_turn", meta.get("dunkest_turn"))
                    if turn_value is not None and "dunkest_turn" in availability.columns:
                        target_rows = availability.loc[
                            pd.to_numeric(availability["dunkest_turn"], errors="coerce").eq(int(turn_value))
                        ]
                    else:
                        target_rows = availability
                    if target_rows.empty:
                        row_timestamp_check = {"passed": True, "target_turn_rows": 0, "undated_rows": 0}
                    elif "observed_at_utc" not in target_rows.columns:
                        row_timestamp_check = {"passed": False, "target_turn_rows": int(len(target_rows)), "undated_rows": int(len(target_rows)), "reason": "target-turn availability rows lack observed_at_utc"}
                        valid_time = False
                    else:
                        observed = pd.to_datetime(target_rows["observed_at_utc"], utc=True, errors="coerce")
                        bad = observed.isna() | observed.ge(kickoffs.min())
                        row_timestamp_check = {"passed": not bool(bad.any()), "target_turn_rows": int(len(target_rows)), "undated_rows": int(observed.isna().sum()), "reason": "ok" if not bad.any() else "target-turn availability observation missing timestamp or at/after kickoff"}
                        valid_time = valid_time and not bool(bad.any())
                except (OSError, ValueError, pd.errors.ParserError) as exc:
                    row_timestamp_check = {"passed": False, "reason": f"cannot validate availability rows: {exc}"}
                    valid_time = False
            per_file.append({"path": data_name, "metadata_present": True, "timestamp_valid": valid_time,
                             "captured_at_utc": capture_time.isoformat() if pd.notna(capture_time) else None,
                             "row_timestamp_check": row_timestamp_check,
                             "reason": "ok" if valid_time else "missing/invalid timestamp or capture/observation at or after earliest kickoff"})
        input_capture_checks[label] = {
            "present": True,
            "metadata_present": all(item["metadata_present"] for item in per_file),
            "timestamp_valid": all(item["timestamp_valid"] for item in per_file),
            "files": per_file,
        }
    pre_match_inputs_complete = all(item["present"] for item in input_capture_checks.values())
    snapshot_capture_metadata_ok = pre_match_inputs_complete and all(
        item["metadata_present"] and item["timestamp_valid"] for item in input_capture_checks.values()
    )
    safe_cutoff, timing_mode = safe_postgame_retrieval_cutoff(mapping["game_datetime_utc"])
    return mapping, {"run_id": manifest.get("run_id", run_dir.name), "run_timestamp_utc": run_time.isoformat(), "season_id": season_id, "gameweek": gw, "mapped_fixtures": int(mapping["nba_game_id"].astype(str).nunique()), "earliest_kickoff_utc": kickoffs.min().isoformat(), "latest_kickoff_utc": kickoffs.max().isoformat(), "minimum_safe_result_retrieval_after_utc": safe_cutoff.isoformat(), "result_retrieval_timing_mode": timing_mode, "snapshot_files_hash_verified": len(files), "pre_match_inputs_complete": pre_match_inputs_complete, "snapshot_capture_metadata_ok": snapshot_capture_metadata_ok, "snapshot_capture_checks": input_capture_checks}


def evaluate_run(run_dir: Path, results_dir: Path | None) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    manifest = read_json(run_dir / "manifest.json")
    mapping, audit = validate_run(run_dir, manifest)
    config = manifest.get("configuration", {})
    season_id, gw = audit["season_id"], audit["gameweek"]
    report = {"status": "not_ready", "season_id": season_id, "gameweek": gw, "run": audit, "checks": [], "metrics": {}, "limitations": []}
    report["checks"].append({
        "check": "pre_match_snapshot_capture_times",
        "passed": audit["snapshot_capture_metadata_ok"],
        "detail": "All required player credits, coach market, injuries, Lineups market and availability snapshots have timestamped sidecars captured before the earliest kickoff."
        if audit["snapshot_capture_metadata_ok"] else "Required inputs or timestamp sidecars are missing/invalid, or at least one capture is not strictly before the earliest kickoff; see run.snapshot_capture_checks.",
    })
    if not audit["pre_match_inputs_complete"]:
        report["limitations"].append("Complete-lineup evaluation requires frozen player credits, coach market, injuries, Lineups market, and availability snapshots.")
    if not audit["snapshot_capture_metadata_ok"]:
        report["limitations"].append("Pre-match input provenance is not authenticated: each required input must have a valid acquisition timestamp before the earliest kickoff.")
    if results_dir is None:
        report["checks"].append({"check": "post_match_results", "passed": False, "detail": "No archived post-match result bundle exists yet."})
        report["limitations"].append("Metrics are withheld until player and coach actual scores are archived with NBA fixture IDs.")
        return report, pd.DataFrame(), pd.DataFrame()

    result_manifest = read_json(results_dir / "manifest.json")
    if str(result_manifest.get("season_id")) != season_id or int(result_manifest.get("dunkest_gameweek", -1)) != gw:
        raise ValueError("Post-match archive season/GW does not match prediction run.")
    if not str(result_manifest.get("source", "")).strip():
        raise ValueError("Post-match archive must identify its source.")
    retrieved = pd.to_datetime(result_manifest.get("retrieved_at_utc"), utc=True, errors="coerce")
    safe_cutoff, timing_mode = safe_postgame_retrieval_cutoff(mapping["game_datetime_utc"])
    if pd.isna(retrieved) or retrieved < safe_cutoff:
        raise ValueError(
            "Post-match archive is earlier than the safe result-collection cutoff "
            f"({safe_cutoff.isoformat()}, mode={timing_mode})."
        )
    expected_hashes = result_manifest.get("sha256", {})
    result_files = {name: results_dir / name for name in ("player_results.parquet", "coach_results.parquet")}
    for name, path in result_files.items():
        if not path.is_file() or expected_hashes.get(name) != sha256(path):
            raise ValueError(f"Missing result file or SHA-256 mismatch: {name}")

    player_actuals, player_audit = canonical_actuals(pd.read_parquet(result_files["player_results.parquet"]), "player", ("actual_pdk", "realized_pdk", "pdk", "score_pdk"))
    coach_actuals, coach_audit = canonical_actuals(pd.read_parquet(result_files["coach_results.parquet"]), "coach", ("actual_coach_pdk", "actual_pdk", "realized_pdk", "pdk", "score_pdk"))
    mapped_ids = set(mapping["nba_game_id"].astype(str))
    for name, data in (("player", player_actuals), ("coach", coach_actuals)):
        extra = sorted(set(data["nba_game_id"]) - mapped_ids)
        if extra:
            raise ValueError(f"{name} results include fixture IDs absent from archived mapping: {extra[:8]}")
    coach_market_entries = [
        entry for entry in manifest.get("pre_match_snapshot", {}).get("files", [])
        if str(entry.get("path", "")).startswith("coach_market_")
    ]
    if not coach_market_entries:
        raise ValueError("No frozen coach-market snapshot in the prediction run.")
    coach_market = pd.read_parquet(run_dir / "pre_match_snapshot" / coach_market_entries[0]["path"])
    if not {"coach", "nba_game_id"}.issubset(coach_market.columns):
        raise ValueError("Frozen coach-market snapshot lacks coach/nba_game_id columns.")
    expected_coach_pairs = {
        (player_key(str(row["coach"])), str(row["nba_game_id"]).strip())
        for _, row in coach_market.iterrows()
        if str(row["coach"]).strip() and str(row["nba_game_id"]).strip() in mapped_ids
    }
    actual_coach_pairs = set(zip(coach_actuals["_key"], coach_actuals["nba_game_id"].astype(str)))
    all_coach_pairs_matched = bool(expected_coach_pairs) and expected_coach_pairs.issubset(actual_coach_pairs)

    predictions = pd.read_parquet(run_dir / "predictions.parquet")
    required = {"player_name", "nba_game_id", "expected_pdk"}
    if not required.issubset(predictions.columns):
        raise ValueError(f"Prediction file missing columns: {sorted(required - set(predictions.columns))}")
    predictions = predictions.copy()
    predictions["_key"] = predictions["player_name"].map(player_key)
    predictions["nba_game_id"] = predictions["nba_game_id"].astype(str).str.strip()
    predictions["expected_pdk"] = pd.to_numeric(predictions["expected_pdk"], errors="coerce")
    lookup = player_actuals.set_index(["_key", "nba_game_id"])["actual_score"]
    keys = pd.MultiIndex.from_arrays([predictions["_key"], predictions["nba_game_id"]])
    predictions["actual_pdk"] = lookup.reindex(keys).to_numpy()
    valid = predictions["_key"].ne("") & np.isfinite(predictions["expected_pdk"]) & np.isfinite(predictions["actual_pdk"])
    matched = predictions.loc[valid].copy()
    if matched.empty:
        raise ValueError("No predicted player-fixture rows match archived player actuals.")
    errors = matched["expected_pdk"] - matched["actual_pdk"]
    mae, rmse, bias = float(np.abs(errors).mean()), float(np.sqrt(np.square(errors).mean())), float(errors.mean())
    p10_cov = p90_cov = interval_cov = interval_width = np.nan
    if {"p10", "p90"}.issubset(matched.columns):
        low, high = pd.to_numeric(matched["p10"], errors="coerce"), pd.to_numeric(matched["p90"], errors="coerce")
        iv = low.notna() & high.notna()
        if iv.any():
            p10_cov = float((matched.loc[iv, "actual_pdk"] >= low[iv]).mean())
            p90_cov = float((matched.loc[iv, "actual_pdk"] <= high[iv]).mean())
            interval_cov = float(((matched.loc[iv, "actual_pdk"] >= low[iv]) & (matched.loc[iv, "actual_pdk"] <= high[iv])).mean())
            interval_width = float((high[iv] - low[iv]).mean())

    lineups = pd.read_parquet(run_dir / "lineups.parquet")
    lineup_rows = []
    if not lineups.empty:
        needed = {"rank", "player_name", "nba_game_id", "coach", "coach_nba_game_id", "dunkest_turn", "slot"}
        if not needed.issubset(lineups.columns):
            raise ValueError(f"Lineup file missing columns: {sorted(needed - set(lineups.columns))}")
        coach_lookup = coach_actuals.set_index(["_key", "nba_game_id"])["actual_score"]
        for rank, roster in lineups.groupby("rank", sort=True):
            player_total = 0.0
            missing = []
            for _, player in roster.iterrows():
                key = player_key(player["player_name"])
                fixture = str(player["nba_game_id"]).strip()
                actual = lookup.get((key, fixture), np.nan)
                if not np.isfinite(actual):
                    missing.append(f"{player['player_name']}@{fixture}")
                    continue
                turn = pd.to_numeric(pd.Series([player.get("dunkest_turn")]), errors="coerce").iloc[0]
                turn_slot_name = f"slot_turn_{int(turn)}" if np.isfinite(turn) else ""
                slot = str(player.get(turn_slot_name, player.get("slot", "Bench"))) if turn_slot_name else str(player.get("slot", "Bench"))
                captain = player_key(player["player_name"]) == player_key(player.get("captain", ""))
                player_total += float(actual) * player_contribution_multiplier(slot in {"Starter", "Captain"} or captain, slot == "Sixth Man", captain)
            coach_name = str(roster["coach"].iloc[0]).strip()
            coach_fixture = str(roster["coach_nba_game_id"].iloc[0]).strip()
            coach_score = coach_lookup.get((player_key(coach_name), coach_fixture), np.nan)
            ntransfers = pd.to_numeric(roster.get("num_transfers", pd.Series(dtype=float)), errors="coerce").dropna()
            ntransfers = float(ntransfers.iloc[0]) if not ntransfers.empty else np.nan
            stored_malus = pd.to_numeric(roster.get("transfer_malus", pd.Series(dtype=float)), errors="coerce").dropna()
            if not stored_malus.empty:
                # The optimizer freezes the round-specific transfer malus with the lineup.
                malus = float(stored_malus.iloc[0])
            elif np.isfinite(ntransfers) and "transfer_penalty" in config:
                malus = ntransfers * float(config["transfer_penalty"])
            else:
                malus = np.nan
            unique_players = int(roster["player_name"].map(player_key).nunique())
            roster_size_valid = len(roster) == 10 and unique_players == 10
            complete = roster_size_valid and not missing and np.isfinite(coach_score) and np.isfinite(malus)
            lineup_rows.append({"rank": int(rank), "selected_player_rows": len(roster), "unique_players": unique_players, "roster_size_valid": roster_size_valid, "missing_player_actuals": len(missing), "missing_players": "; ".join(missing[:10]), "coach": coach_name, "coach_nba_game_id": coach_fixture, "actual_coach_pdk": float(coach_score) if np.isfinite(coach_score) else np.nan, "num_transfers": ntransfers, "transfer_malus": malus, "actual_player_score": player_total if roster_size_valid and not missing else np.nan, "actual_team_score": player_total + float(coach_score) - malus if complete else np.nan, "complete": bool(complete)})
    lineup_metrics = pd.DataFrame(lineup_rows)
    complete_lineups = lineup_metrics.loc[lineup_metrics["complete"]] if not lineup_metrics.empty else pd.DataFrame()
    all_player_actuals_matched = len(matched) == len(predictions)
    all_coach_fixtures_matched = all_coach_pairs_matched
    report["status"] = (
        "ready"
        if not lineup_metrics.empty
        and len(complete_lineups) == len(lineup_metrics)
        and all_player_actuals_matched
        and all_coach_fixtures_matched
        and audit["pre_match_inputs_complete"]
        and audit["snapshot_capture_metadata_ok"]
        else "partial"
    )
    report["actuals"] = {"player_results": player_audit, "coach_results": coach_audit, "results_archive": str(results_dir), "source": result_manifest["source"], "retrieved_at_utc": retrieved.isoformat()}
    report["checks"] = [
        {"check": "snapshot_hashes", "passed": True, "detail": f"Verified {audit['snapshot_files_hash_verified']} pre-match files."},
        {"check": "pre_tipoff_run", "passed": True, "detail": "Forecast run precedes the earliest kickoff."},
        {"check": "pre_match_snapshot_capture_times", "passed": audit["snapshot_capture_metadata_ok"], "detail": "All required input capture times precede kickoff." if audit["snapshot_capture_metadata_ok"] else "Required inputs or timestamp sidecars are missing/invalid or captured at/after kickoff."},
        {"check": "player_actual_coverage", "passed": len(matched) == len(predictions), "detail": f"{len(matched)}/{len(predictions)} prediction rows linked to actuals."},
        {"check": "coach_actual_coverage", "passed": all_coach_pairs_matched, "detail": f"Coach actuals cover {len(expected_coach_pairs & actual_coach_pairs)}/{len(expected_coach_pairs)} frozen coach-fixture pairs."},
        {"check": "complete_lineups", "passed": not lineup_metrics.empty and len(complete_lineups) == len(lineup_metrics), "detail": f"{len(complete_lineups)}/{len(lineup_metrics)} lineup ranks fully scored."},
    ]
    report["metrics"] = {"predicted_player_fixture_rows": len(predictions), "matched_player_fixture_rows": len(matched), "player_actual_coverage": len(matched) / len(predictions) if len(predictions) else np.nan, "player_mae": mae, "player_rmse": rmse, "player_bias": bias, "p10_coverage": p10_cov, "p90_coverage": p90_cov, "interval_80_coverage": interval_cov, "mean_interval_width": interval_width, "lineup_ranks": len(lineup_metrics), "complete_lineup_ranks": len(complete_lineups), "rank1_realized_team_score": float(complete_lineups.loc[complete_lineups["rank"].eq(1), "actual_team_score"].iloc[0]) if complete_lineups["rank"].eq(1).any() else np.nan, "best_of_k_realized_team_score": float(complete_lineups["actual_team_score"].max()) if not complete_lineups.empty else np.nan}
    if report["status"] != "ready":
        report["limitations"].append("Incomplete actual player/coach fixture links make one or more lineup scores unavailable; no missing score is replaced with zero.")
    return report, matched, lineup_metrics


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a frozen Dunkest forecast against immutable post-match results.")
    parser.add_argument("--data-dir", default="data", help="Data root containing immutable post-match archives.")
    parser.add_argument("--season-id", default="26")
    parser.add_argument("--gameweek", type=int, default=1)
    parser.add_argument("--run-id", help="Prediction run ID under data/predictions.")
    parser.add_argument("--run-dir", help="Explicit frozen prediction-run directory, including isolated workspace runs.")
    parser.add_argument("--results-dir")
    parser.add_argument("--output-dir", default="reports/backtest")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    run_dir = resolve_run_dir(data_dir, args.season_id, args.gameweek, args.run_id, args.run_dir)
    manifest = read_json(run_dir / "manifest.json")
    config = manifest.get("configuration", {})
    season_id = str(config.get("season_id", args.season_id))
    gw = int(config.get("target_gameweek", args.gameweek))
    results_dir = latest_results(data_dir, season_id, gw, args.results_dir)
    report, matched, lineups = evaluate_run(run_dir, results_dir)
    run_id = str(manifest.get("run_id", run_dir.name))
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"post_match_evaluation_{run_id}"
    (out / f"{stem}.json").write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Post-match evaluation — {run_id}", "", f"- Status: **{report['status']}**", f"- Season ID / GW: {season_id} / {gw}", ""]
    lines.append("## Metrics")
    lines.append("")
    for key, value in report.get("metrics", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Checks", ""])
    for check in report.get("checks", []):
        lines.append(f"- [{'x' if check['passed'] else ' '}] {check['check']}: {check['detail']}")
    if report.get("limitations"):
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in report["limitations"])
    (out / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    lineups.to_csv(out / f"{stem}_lineups.csv", index=False)
    print(json.dumps({"status": report["status"], "run": str(run_dir), "results": str(results_dir) if results_dir else None, "metrics": json_safe(report.get("metrics", {})), "outputs": [str(out / f"{stem}.json"), str(out / f"{stem}.md"), str(out / f"{stem}_lineups.csv")]}, indent=2))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
