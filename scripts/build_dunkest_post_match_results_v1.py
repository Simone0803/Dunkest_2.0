from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.names import player_key
from dunkest.report.artifacts import save_post_match_snapshot
from dunkest.rules.coach import coach_points_from_game
from dunkest.rules.pdk import pdk_from_boxscore_row
from dunkest.backtest.timing import safe_postgame_retrieval_cutoff


def read_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            return pd.DataFrame(value)
        if isinstance(value, dict):
            for key in ("data", "results", "records", "games"):
                if isinstance(value.get(key), list):
                    return pd.DataFrame(value[key])
        raise ValueError(f"Cannot identify row records in JSON file: {path}")
    raise ValueError(f"Unsupported input format: {path.suffix}")


def fingerprint_file(path: Path) -> dict:
    """Hash one exact source file and reject files that changed during hashing."""
    resolved = path.expanduser().resolve()
    before = resolved.stat()
    digest = hashlib.sha256()
    with resolved.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    after = resolved.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Source file changed while fingerprinting: {resolved}")
    return {
        "path": str(resolved),
        "size_bytes": int(after.st_size),
        "sha256": digest.hexdigest(),
    }


def resolve_run_dir(data_dir: Path, run_id: str | None = None, run_dir: str | Path | None = None) -> Path:
    """Resolve a frozen run by ID or by explicit path, including isolated workspaces."""
    if run_dir:
        candidate = Path(run_dir).expanduser().resolve()
    elif run_id:
        candidate = data_dir / "predictions" / run_id
    else:
        raise ValueError("provide either --run-id or --run-dir")
    manifest_path = candidate / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Prediction manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resolved_id = str(manifest.get("run_id", candidate.name))
    if run_id and run_id != resolved_id:
        raise ValueError(f"--run-id {run_id!r} does not match manifest run_id {resolved_id!r}.")
    return candidate


def choose(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> str:
    for column in columns:
        if column in frame.columns:
            return column
    raise ValueError(f"{label}: none of the required columns found: {columns}")


def game_date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.strftime("%Y-%m-%d")


def _verified(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().casefold() in {"true", "1", "yes"}


def prepare_fixture_index(mapping: pd.DataFrame, gameweek: int) -> tuple[pd.DataFrame, dict]:
    required = {"nba_game_id", "home_team", "away_team", "game_datetime_utc", "dunkest_gameweek", "mapping_verified"}
    missing = sorted(required - set(mapping.columns))
    if missing:
        raise ValueError(f"Fixture mapping missing required columns: {missing}")
    fixtures = mapping.loc[pd.to_numeric(mapping["dunkest_gameweek"], errors="coerce").eq(gameweek)].copy()
    fixtures = fixtures.loc[fixtures["mapping_verified"].map(_verified)]
    if fixtures.empty:
        raise ValueError(f"No verified fixture mapping for GW{gameweek}.")
    if {"source_retrieved_at_utc", "raw_payload_sha256"}.issubset(fixtures.columns):
        kickoff = pd.to_datetime(fixtures["game_datetime_utc"], utc=True, errors="coerce")
        retrieved = pd.to_datetime(fixtures["source_retrieved_at_utc"], utc=True, errors="coerce")
        if kickoff.isna().any() or retrieved.isna().any() or (retrieved > kickoff).any():
            raise ValueError("Fixture mapping has invalid or post-tipoff retrieval timestamps.")
        if fixtures["raw_payload_sha256"].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError("Fixture mapping lacks raw payload hashes.")
    if fixtures["nba_game_id"].astype(str).duplicated().any():
        raise ValueError("Fixture mapping contains duplicate NBA game IDs for the gameweek.")
    date_col = "game_date_local" if "game_date_local" in fixtures.columns else "game_datetime_utc"
    fixtures["_date"] = game_date_series(fixtures[date_col])
    if fixtures["_date"].isna().any():
        raise ValueError("Fixture mapping includes invalid local game dates.")
    return fixtures, {"fixture_count": int(len(fixtures)), "fixture_ids": sorted(fixtures["nba_game_id"].astype(str).tolist())}


def build_player_actuals(
    predictions: pd.DataFrame,
    player_market: pd.DataFrame,
    fixtures: pd.DataFrame,
    official_games: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    pred_required = {"player_name", "nba_game_id"}
    market_required = {"player_name", "team_code"}
    if not pred_required.issubset(predictions.columns):
        raise ValueError(f"Predictions missing columns: {sorted(pred_required - set(predictions.columns))}")
    if not market_required.issubset(player_market.columns):
        raise ValueError(f"Player market missing columns: {sorted(market_required - set(player_market.columns))}")
    name_col = choose(official_games, ("_requested_player_name", "dunkest_player_name", "player_name", "name"), "official player results")
    opponent_col = choose(official_games, ("opponentTeamCode", "opponent_team_code", "opponent"), "official player results")
    date_col = choose(official_games, ("gameDate", "game_date", "GAME_DATE", "date"), "official player results")
    pdk_col = choose(official_games, ("pdk", "actual_pdk", "score_pdk"), "official player results")
    valid_col = choose(official_games, ("gameValidForDunkest", "game_valid_for_dunkest"), "official player results")

    market = player_market[["player_name", "team_code"]].copy()
    market["player_key"] = market["player_name"].map(player_key)
    market["team_code"] = market["team_code"].astype(str).str.upper().str.strip()
    market = market.loc[market["player_key"].ne("")]
    # A normalized player identity must map to exactly one team in the frozen roster.
    multi_team = market.groupby("player_key")["team_code"].nunique()
    if (multi_team > 1).any():
        bad = multi_team[multi_team > 1].index.tolist()[:8]
        raise ValueError(f"Players have conflicting team assignments in the frozen market: {bad}")
    name_team = market.drop_duplicates("player_key").set_index("player_key")
    canonical_names = market.drop_duplicates("player_key").set_index("player_key")["player_name"].to_dict()

    fixture_rows = []
    for _, f in fixtures.iterrows():
        date = str(f["_date"])
        game_id = str(f["nba_game_id"])
        home = str(f["home_team"]).upper().strip()
        away = str(f["away_team"]).upper().strip()
        fixture_rows.append({"_date": date, "team": home, "opponent": away, "nba_game_id": game_id})
        fixture_rows.append({"_date": date, "team": away, "opponent": home, "nba_game_id": game_id})
    by_matchup: dict[tuple[str, str, str], list[str]] = {}
    for item in fixture_rows:
        by_matchup.setdefault((item["_date"], item["team"], item["opponent"]), []).append(item["nba_game_id"])

    raw = official_games.copy()
    raw["_player_key"] = raw[name_col].map(player_key)
    raw["_opponent"] = raw[opponent_col].astype(str).str.upper().str.strip()
    raw["_date"] = game_date_series(raw[date_col])
    raw["_score"] = pd.to_numeric(raw[pdk_col], errors="coerce")
    raw["_valid"] = raw[valid_col].astype(str).str.lower().isin({"true", "1", "yes"})
    target_keys = set(predictions["player_name"].map(player_key))
    target_dates = set(fixtures["_date"].astype(str))
    raw = raw.loc[
        raw["_valid"]
        & raw["_player_key"].isin(target_keys)
        & raw["_player_key"].isin(name_team.index)
        & raw["_date"].isin(target_dates)
        & np.isfinite(raw["_score"])
    ].copy()

    mapped_rows = []
    unresolved_rows = []
    for _, row in raw.iterrows():
        key = row["_player_key"]
        team = str(name_team.loc[key, "team_code"])
        matchup_key = (str(row["_date"]), team, str(row["_opponent"]))
        candidates = by_matchup.get(matchup_key, [])
        if len(candidates) != 1:
            unresolved_rows.append({
                "player_name": str(row[name_col]),
                "player_key": key,
                "team": team,
                "opponent": str(row["_opponent"]),
                "game_date": str(row["_date"]),
                "candidate_fixture_count": len(candidates),
                "reason": "no_unique_fixture_match",
            })
            continue
        mapped_rows.append({
            "player_name": canonical_names.get(key, str(row[name_col])),
            "_key": key,
            "nba_game_id": candidates[0],
            "actual_pdk": float(row["_score"]),
        })
    actuals = pd.DataFrame(mapped_rows, columns=["player_name", "_key", "nba_game_id", "actual_pdk"])
    if not actuals.empty:
        actuals["nba_game_id"] = actuals["nba_game_id"].astype(str)
        duplicate = actuals.duplicated(["_key", "nba_game_id"], keep=False)
        if duplicate.any():
            counts = actuals.loc[duplicate].groupby(["_key", "nba_game_id"])["actual_pdk"].nunique()
            if (counts > 1).any():
                raise ValueError("Official results have conflicting PDK values for a player-fixture pair.")
            actuals = actuals.drop_duplicates(["_key", "nba_game_id"], keep="last")
    actuals = actuals[["player_name", "nba_game_id", "actual_pdk"]].copy()

    expected = predictions[["player_name", "nba_game_id"]].copy()
    expected["_key"] = expected["player_name"].map(player_key)
    expected["nba_game_id"] = expected["nba_game_id"].astype(str).str.strip()
    expected = expected.drop_duplicates(["_key", "nba_game_id"])
    actuals["_key"] = actuals["player_name"].map(player_key)
    actual_key_set = set(zip(actuals["_key"], actuals["nba_game_id"].astype(str)))
    expected["actual_found"] = [(key, game_id) in actual_key_set for key, game_id in zip(expected["_key"], expected["nba_game_id"])]
    missing = expected.loc[~expected["actual_found"]].copy()
    if not missing.empty:
        missing["reason"] = "no_valid_official_actual_for_prediction_fixture"
    actuals = actuals.drop(columns=["_key"], errors="ignore")
    unresolved = pd.DataFrame(unresolved_rows)
    audit = {
        "official_rows": int(len(official_games)),
        "official_valid_rows_considered": int(len(raw)),
        "mapped_player_fixture_actuals": int(len(actuals)),
        "expected_player_fixture_pairs": int(len(expected)),
        "matched_prediction_pairs": int(expected["actual_found"].sum()),
        "prediction_coverage": float(expected["actual_found"].mean()) if len(expected) else 0.0,
        "unresolved_official_rows": int(len(unresolved)),
        "missing_prediction_pairs": int(len(missing)),
        "validity_column": valid_col,
        "score_column": pdk_col,
        "name_column": name_col,
        "date_column": date_col,
        "opponent_column": opponent_col,
    }
    return actuals, pd.concat([missing, unresolved], ignore_index=True, sort=False), audit


def _finite_number(value: object) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) and np.isfinite(float(parsed)) else np.nan


def _parse_minutes(value: object) -> float:
    if isinstance(value, str) and ":" in value:
        parts = value.strip().split(":", maxsplit=1)
        try:
            minutes = float(parts[0])
            seconds = float(parts[1])
            if 0 <= seconds < 60:
                return minutes + seconds / 60.0
        except (TypeError, ValueError):
            pass
    return _finite_number(value)


def build_player_outcome_panel(
    predictions: pd.DataFrame,
    player_market: pd.DataFrame,
    fixtures: pd.DataFrame,
    official_games: pd.DataFrame,
    nba_player_logs: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Return one outcome row per frozen candidate; missing logs stay missing."""
    if not {"player_name", "nba_game_id"}.issubset(predictions.columns):
        raise ValueError("Frozen forecasts need player_name and nba_game_id columns.")
    if not {"player_name", "team_code"}.issubset(player_market.columns):
        raise ValueError("Frozen player market needs player_name and team_code columns.")

    official_actuals, official_unresolved, official_audit = build_player_actuals(
        predictions, player_market, fixtures, official_games
    ) if not official_games.empty else (
        pd.DataFrame(columns=["player_name", "nba_game_id", "actual_pdk"]),
        pd.DataFrame(),
        {"mapped_player_fixture_actuals": 0, "expected_player_fixture_pairs": len(predictions), "prediction_coverage": 0.0},
    )
    ambiguous_official: set[tuple[str, str]] = set()
    if not official_unresolved.empty and {"player_key", "game_date", "candidate_fixture_count"}.issubset(official_unresolved):
        for _, unresolved in official_unresolved.iterrows():
            if _finite_number(unresolved.get("candidate_fixture_count")) > 1:
                ambiguous_official.add((str(unresolved["player_key"]), str(unresolved["game_date"])))
    market = player_market.copy()
    market["player_key"] = market["player_name"].map(player_key)
    market["team_code"] = market["team_code"].astype(str).str.upper().str.strip()
    team_counts = market.groupby("player_key")["team_code"].nunique()
    if (team_counts > 1).any():
        raise ValueError("Frozen candidate identity maps to multiple NBA teams.")
    market = market.drop_duplicates("player_key", keep="first").set_index("player_key")

    fixture_by_id = {
        str(row["nba_game_id"]): row
        for _, row in fixtures.iterrows()
        if str(row.get("nba_game_id", "")).strip()
    }
    nba_by_key: dict[tuple[str, str], list[pd.Series]] = {}
    if not nba_player_logs.empty:
        game_col = choose(nba_player_logs, ("Game_ID", "GAME_ID", "game_id", "gameId"), "NBA player logs")
        name_col = choose(nba_player_logs, ("PLAYER_NAME", "player_name", "name"), "NBA player logs")
        team_col = choose(nba_player_logs, ("TEAM_ABBREVIATION", "team_abbreviation", "team"), "NBA player logs")
        minutes_col = choose(nba_player_logs, ("MIN", "minutes", "MINUTES", "MIN_SEC"), "NBA player logs")
        logs = nba_player_logs.copy()
        logs["_game"] = logs[game_col].astype(str).str.strip()
        logs["_player_key"] = logs[name_col].map(player_key)
        logs["_team"] = logs[team_col].astype(str).str.upper().str.strip()
        logs["_minutes"] = logs[minutes_col].map(_parse_minutes)
        for _, row in logs.iterrows():
            nba_by_key.setdefault((row["_game"], row["_player_key"]), []).append(row)

    official = official_actuals.copy()
    official["player_key"] = official["player_name"].map(player_key) if not official.empty else pd.Series(dtype=str)
    official_lookup = {
        (str(row["nba_game_id"]), str(row["player_key"])): _finite_number(row.get("actual_pdk"))
        for _, row in official.iterrows()
    }
    proxy_fields = {
        "PTS", "OREB", "DREB", "AST", "STL", "BLK", "BLKA", "TOV",
        "FG3M", "FGA", "FGM", "FTA", "FTM",
    }
    rows: list[dict] = []
    for _, forecast in predictions.iterrows():
        name = str(forecast.get("player_name", "")).strip()
        key = player_key(name)
        raw_game_id = forecast.get("nba_game_id")
        game_id = "" if pd.isna(raw_game_id) else str(raw_game_id).strip()
        team = str(forecast.get("team", "")).upper().strip()
        market_team = str(market.loc[key, "team_code"]) if key in market.index else ""
        if not team:
            team = market_team
        team_matches_market = bool(team and market_team and team == market_team)
        fixture = fixture_by_id.get(game_id)
        fixture_ok = bool(
            fixture is not None
            and _verified(fixture.get("mapping_verified", False))
            and team_matches_market
            and team in {str(fixture.get("home_team", "")).upper(), str(fixture.get("away_team", "")).upper()}
        )
        opponent = str(forecast.get("opponent", "")).upper().strip()
        if fixture_ok:
            expected_opp = str(
                fixture.get("away_team") if team == str(fixture.get("home_team", "")).upper()
                else fixture.get("home_team")
            ).upper().strip()
            fixture_ok = not opponent or opponent == expected_opp
            if not opponent:
                opponent = expected_opp
        actual_min = np.nan
        minutes_status = "outcome_missing"
        proxy_pdk = np.nan
        matching_logs = nba_by_key.get((game_id, key), []) if game_id else []
        if fixture_ok and matching_logs:
            wrong_team_rows = [row for row in matching_logs if str(row.get("_team", "")) != team]
            if wrong_team_rows:
                minutes_status = "outcome_ambiguous"
            matching_logs = [row for row in matching_logs if str(row.get("_team", "")) == team]
            minutes_values = sorted(set(float(row["_minutes"]) for row in matching_logs if pd.notna(row["_minutes"])))
            if minutes_status == "outcome_ambiguous":
                pass
            elif len(matching_logs) != 1 or len(minutes_values) != 1:
                minutes_status = "outcome_ambiguous"
            elif minutes_values[0] > 0:
                actual_min = minutes_values[0]
                minutes_status = "appeared"
                box = matching_logs[0]
                if proxy_fields.issubset(box.index) and all(pd.notna(box[field]) for field in proxy_fields):
                    proxy_pdk = pdk_from_boxscore_row(box, team_won=None)
            elif minutes_values[0] == 0:
                actual_min = 0.0
                comment = " ".join(
                    str(matching_logs[0].get(column, ""))
                    for column in ("COMMENT", "comment", "STATUS", "status")
                ).upper()
                minutes_status = "dnp_documented" if "DNP" in comment or "INACTIVE" in comment else "zero_minutes_verified"
        elif not fixture_ok:
            minutes_status = "fixture_unverified"

        fixture_date = str(fixture.get("_date", "")) if fixture is not None else ""
        is_official_ambiguous = (key, fixture_date) in ambiguous_official
        actual_official = official_lookup.get((game_id, key), np.nan) if fixture_ok and not is_official_ambiguous else np.nan
        canonical_id = forecast.get("canonical_player_id", key)
        if pd.isna(canonical_id) or not str(canonical_id).strip():
            canonical_id = key
        if minutes_status == "outcome_missing" and np.isfinite(actual_official):
            minutes_status = "official_pdk_only"
        rows.append({
            **forecast.to_dict(),
            "player_key": key,
            "canonical_player_id": canonical_id,
            "fixture_verified": fixture_ok,
            "outcome_status": minutes_status,
            "actual_minutes": actual_min,
            "actual_minutes_source": "nba_player_game_log" if np.isfinite(actual_min) else None,
            "actual_pdk_official": actual_official,
            "actual_pdk": actual_official,
            "actual_pdk_status": "official_verified" if np.isfinite(actual_official) else ("ambiguous" if is_official_ambiguous else "missing"),
            "actual_pdk_source": "official_dunkest" if np.isfinite(actual_official) else None,
            "actual_pdk_nba_proxy": proxy_pdk,
            "actual_pdk_nba_proxy_source": "nba_boxscore_rule_proxy" if np.isfinite(proxy_pdk) else None,
            "official_outcome_pending": not np.isfinite(actual_official),
            "ambiguous_outcome": minutes_status == "outcome_ambiguous",
            "ambiguous_official_pdk": bool(is_official_ambiguous),
        })
    panel = pd.DataFrame(rows)
    if not panel.empty:
        keys = list(zip(panel["player_key"], panel["nba_game_id"].fillna("").astype(str)))
        if len(keys) != len(set(keys)):
            raise ValueError("Frozen forecast contains duplicate player-fixture candidate rows.")
    return panel, {
        **official_audit,
        "candidate_rows": int(len(panel)),
        "minutes_reconciled": int(pd.to_numeric(panel.get("actual_minutes"), errors="coerce").notna().sum()),
        "verified_zero_minutes": int(pd.to_numeric(panel.get("actual_minutes"), errors="coerce").eq(0.0).sum()),
        "documented_dnp": int(panel.get("outcome_status", pd.Series(dtype=str)).eq("dnp_documented").sum()),
        "missing_or_ambiguous": int(panel.get("outcome_status", pd.Series(dtype=str)).isin({"outcome_missing", "outcome_ambiguous", "fixture_unverified"}).sum()),
        "ambiguous_official_pdk": int(panel.get("actual_pdk_status", pd.Series(dtype=str)).eq("ambiguous").sum()),
    }


def evaluate_player_forecast_panel(panel: pd.DataFrame) -> dict:
    """Summarize coverage and errors using only valid, explicitly sourced labels."""
    result = {
        "candidate_count": int(len(panel)),
        "reconciled_outcomes": int(panel.get("outcome_status", pd.Series(dtype=str)).isin({"appeared", "zero_minutes_verified", "dnp_documented", "official_pdk_only"}).sum()),
        "verified_zero_minutes": int(pd.to_numeric(panel.get("actual_minutes"), errors="coerce").eq(0.0).sum()),
        "documented_dnp": int(panel.get("outcome_status", pd.Series(dtype=str)).eq("dnp_documented").sum()),
        "missing_outcomes": int(panel.get("outcome_status", pd.Series(dtype=str)).eq("outcome_missing").sum()),
        "ambiguous_outcomes": int(panel.get("outcome_status", pd.Series(dtype=str)).isin({"outcome_ambiguous", "fixture_unverified"}).sum()),
        "ambiguous_official_pdk": int(panel.get("actual_pdk_status", pd.Series(dtype=str)).eq("ambiguous").sum()),
    }
    result["outcome_coverage"] = (
        result["reconciled_outcomes"] / result["candidate_count"] if result["candidate_count"] else 0.0
    )
    result["minutes_coverage"] = (
        int(pd.to_numeric(panel.get("actual_minutes", pd.Series(dtype=float)), errors="coerce").notna().sum())
        / result["candidate_count"] if result["candidate_count"] else 0.0
    )
    result["official_pdk_coverage"] = (
        int(pd.to_numeric(panel.get("actual_pdk_official", pd.Series(dtype=float)), errors="coerce").notna().sum())
        / result["candidate_count"] if result["candidate_count"] else 0.0
    )
    for label, prediction_col, actual_col in (
        ("minutes", "expected_min", "actual_minutes"),
        ("pdk_official", "expected_pdk", "actual_pdk_official"),
    ):
        if prediction_col not in panel or actual_col not in panel:
            result[label] = {"n": 0, "mae": None, "rmse": None, "bias": None}
            continue
        predicted = pd.to_numeric(panel[prediction_col], errors="coerce")
        actual = pd.to_numeric(panel[actual_col], errors="coerce")
        valid = predicted.notna() & actual.notna() & np.isfinite(predicted) & np.isfinite(actual)
        error = predicted.loc[valid] - actual.loc[valid]
        result[label] = {
            "n": int(valid.sum()),
            "mae": float(error.abs().mean()) if valid.any() else None,
            "rmse": float(np.sqrt(np.square(error).mean())) if valid.any() else None,
            "bias": float(error.mean()) if valid.any() else None,
        }
    return result


def _canonical_frame_hash(frame: pd.DataFrame, keys: list[str]) -> str:
    ordered = frame.copy()
    present_keys = [column for column in keys if column in ordered]
    if present_keys:
        ordered = ordered.sort_values(present_keys, kind="stable", na_position="last")
    payload = ordered.to_json(orient="records", date_format="iso", double_precision=15)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evaluation_markdown(evaluation: dict, run_id: str, certification: dict) -> str:
    metrics = []
    for key, label, unit in (("minutes", "Minuti", "min"), ("pdk_official", "PDK ufficiale", "PDK")):
        item = evaluation.get(key, {})
        metrics.append(
            f"| {label} | {item.get('n', 0)} | {item.get('mae')} | {item.get('rmse')} | {item.get('bias')} | {unit} |"
        )
    return "\n".join([
        "# Valutazione forecast giocatori",
        "",
        f"Run: `{run_id}`",
        f"Certificazione pre-lock: `{bool(certification.get('pre_lock_eligible', False))}`",
        f"Motivo: {certification.get('reason', 'evidenza di cutoff mancante')}",
        "",
        f"Candidati: {evaluation.get('candidate_count', 0)}; esiti riconciliati: {evaluation.get('reconciled_outcomes', 0)}; copertura: {evaluation.get('outcome_coverage', 0.0):.1%}.",
        f"Copertura minuti: {evaluation.get('minutes_coverage', 0.0):.1%}; copertura PDK ufficiale: {evaluation.get('official_pdk_coverage', 0.0):.1%}.",
        f"Zero minuti verificati: {evaluation.get('verified_zero_minutes', 0)}; DNP documentati: {evaluation.get('documented_dnp', 0)}; mancanti: {evaluation.get('missing_outcomes', 0)}; ambigui/non verificabili: {evaluation.get('ambiguous_outcomes', 0)}; PDK ufficiali ambigui: {evaluation.get('ambiguous_official_pdk', 0)}.",
        "",
        "| Target | N | MAE | RMSE | Bias (previsto − effettivo) | Unità |",
        "|---|---:|---:|---:|---:|---|",
        *metrics,
        "",
        "Le metriche PDK usano soltanto `actual_pdk_official`; `actual_pdk_nba_proxy` resta separato e non entra nell'etichetta ufficiale. Le metriche minuti includono solo righe NBA esplicite con minuti numerici, inclusi gli zero esplicitamente presenti. L'assenza di una riga nei log resta esito mancante.",
        "",
    ])


def verify_immutable_prelock_bundle(run_dir: Path, run_manifest: dict) -> tuple[Path, dict]:
    """Verify the canonical pre-lock archive and registry before outcome use."""
    archive_manifest_path = run_dir / "archive_manifest.json"
    if not archive_manifest_path.is_file():
        raise ValueError("Run is not an immutable pre-lock archive; refusing certification or outcome reconciliation.")
    archive_manifest = json.loads(archive_manifest_path.read_text(encoding="utf-8"))
    current_files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "archive_manifest.json":
            current_files.append({
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    if current_files != archive_manifest.get("files", []):
        raise ValueError("Pre-lock archive integrity check failed.")
    run_id = str(run_manifest.get("run_id", run_dir.name))
    registry_path = run_dir.parents[2] / "registry" / f"{run_id}.json"
    if not registry_path.is_file():
        raise ValueError("Immutable pre-lock registry record is missing.")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(archive_manifest_path.read_bytes()).hexdigest()
    if registry.get("archive_manifest_sha256") != manifest_hash:
        raise ValueError("Pre-lock archive manifest does not match its registry hash.")
    for filename, field in (("predictions.parquet", "predictions_sha256"), ("lineups.parquet", "lineups_sha256")):
        path = run_dir / filename
        if not path.is_file() or registry.get(field) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"Frozen {filename} hash does not match its immutable registry.")
    forecast_path = run_dir / "player_forecast_snapshot.parquet"
    if (
        not forecast_path.is_file()
        or registry.get("player_forecast_snapshot_sha256") != hashlib.sha256(forecast_path.read_bytes()).hexdigest()
    ):
        raise ValueError("Frozen all-candidate forecast hash does not match its immutable registry.")
    if not archive_manifest.get("pre_lock_eligible") or not registry.get("pre_lock_eligible"):
        raise ValueError("Pre-lock archive is incomplete or not certified eligible.")
    if registry.get("run_id") != run_id or run_manifest.get("run_id") != run_id:
        raise ValueError("Pre-lock run identity differs across archive and registry.")
    return registry_path, archive_manifest


def validate_frozen_forecast(run_dir: Path, run_manifest: dict) -> tuple[pd.DataFrame, dict]:
    registry_path, archive_manifest = verify_immutable_prelock_bundle(run_dir, run_manifest)
    descriptor = run_manifest.get("player_forecast_snapshot", {})
    # Resolve only inside the immutable run copy, never against a mutable source
    # directory recorded before the run was archived.
    path = run_dir / Path(descriptor.get("path", "player_forecast_snapshot.parquet")).name
    if not path.is_file():
        raise ValueError("Frozen all-candidate player forecast snapshot is missing; no retrospective reconstruction is allowed.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != descriptor.get("sha256"):
        raise ValueError("Frozen player forecast snapshot hash mismatch.")
    certification = descriptor.get("certification", {})
    forecasted_at = pd.to_datetime(descriptor.get("forecast_timestamp_utc"), errors="coerce", utc=True)
    cutoff = pd.to_datetime(descriptor.get("prediction_cutoff_utc"), errors="coerce", utc=True)
    run_time = pd.to_datetime(run_manifest.get("timestamp"), errors="coerce", utc=True)
    if (
        not certification.get("pre_lock_eligible", False)
        or not certification.get("exact_dunkest_cutoff_verified", False)
        or not descriptor.get("cutoff_verified", False)
        or len(str(descriptor.get("cutoff_source_sha256", ""))) != 64
        or pd.isna(forecasted_at) or pd.isna(cutoff) or pd.isna(run_time)
        or forecasted_at >= cutoff or run_time >= cutoff
    ):
        raise ValueError(
            "Frozen forecast is not certified pre-lock: missing verification or forecast/run timestamp is at/after cutoff."
        )
    forecasts = pd.read_parquet(path)
    if len(forecasts) != int(descriptor.get("candidate_rows", -1)):
        raise ValueError("Frozen candidate forecast row count differs from its manifest.")
    return forecasts, {
        **certification,
        "archive_manifest_sha256": hashlib.sha256((run_dir / "archive_manifest.json").read_bytes()).hexdigest(),
        "registry_path": str(registry_path),
        "archive_id": archive_manifest.get("run_id"),
    }


def build_coach_actuals(
    coach_market: pd.DataFrame,
    fixtures: pd.DataFrame,
    team_logs: pd.DataFrame,
    player_logs: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    required = {"coach", "team", "coach_cr", "opponent", "opponent_coach_cr", "nba_game_id"}
    if not required.issubset(coach_market.columns):
        raise ValueError(f"Coach market missing columns: {sorted(required - set(coach_market.columns))}")
    game_col = choose(team_logs, ("Game_ID", "GAME_ID", "game_id", "gameId"), "team logs")
    team_col = choose(team_logs, ("TEAM_ABBREVIATION", "team_abbreviation", "team"), "team logs")
    points_col = choose(team_logs, ("PTS", "points", "team_points"), "team logs")
    logs = team_logs.copy()
    logs["_game"] = logs[game_col].astype(str).str.strip()
    logs["_team"] = logs[team_col].astype(str).str.upper().str.strip()
    logs["_pts"] = pd.to_numeric(logs[points_col], errors="coerce")
    # Team-level NBA logs usually report MIN=240 even after overtime. Infer OT only
    # from summed player minutes; otherwise leave the coach outcome unresolved.
    overtime_by_game: dict[str, bool] = {}
    if player_logs is not None and not player_logs.empty:
        player_game_col = choose(player_logs, ("Game_ID", "GAME_ID", "game_id", "gameId"), "player logs")
        player_team_col = choose(player_logs, ("TEAM_ABBREVIATION", "team_abbreviation", "team"), "player logs")
        player_min_col = choose(player_logs, ("MIN", "minutes", "MINUTES", "MIN_SEC"), "player logs")
        plogs = player_logs.copy()
        plogs["_game"] = plogs[player_game_col].astype(str).str.strip()
        plogs["_team"] = plogs[player_team_col].astype(str).str.upper().str.strip()
        plogs["_minutes"] = pd.to_numeric(plogs[player_min_col], errors="coerce")
        if plogs["_minutes"].isna().all():
            plogs["_minutes"] = pd.to_timedelta(plogs[player_min_col], errors="coerce").dt.total_seconds() / 60.0
        sums = plogs.dropna(subset=["_minutes"]).groupby(["_game", "_team"])["_minutes"].sum()
        for _, fixture in fixtures.iterrows():
            game_id = str(fixture["nba_game_id"])
            teams = [str(fixture["home_team"]).upper().strip(), str(fixture["away_team"]).upper().strip()]
            team_minutes = [sums.get((game_id, team), np.nan) for team in teams]
            if all(np.isfinite(value) for value in team_minutes):
                overtime_by_game[game_id] = bool(max(team_minutes) > 240.25)

    fixture_ids = set(fixtures["nba_game_id"].astype(str))
    fixture_teams = {
        str(row["nba_game_id"]): {
            str(row["home_team"]).upper().strip(), str(row["away_team"]).upper().strip()
        }
        for _, row in fixtures.iterrows()
    }
    rows = []
    for _, row in coach_market.iterrows():
        game_id = str(row.get("nba_game_id", "")).strip()
        team = str(row.get("team", "")).upper().strip()
        opponent = str(row.get("opponent", "")).upper().strip()
        coach = str(row.get("coach", "")).strip()
        coach_cr = pd.to_numeric(pd.Series([row.get("coach_cr")]), errors="coerce").iloc[0]
        opp_cr = pd.to_numeric(pd.Series([row.get("opponent_coach_cr")]), errors="coerce").iloc[0]
        if game_id not in fixture_ids or not coach or not team or not opponent or not np.isfinite(coach_cr) or not np.isfinite(opp_cr):
            continue
        if {team, opponent} != fixture_teams.get(game_id, set()):
            continue
        # Missing player-minute evidence means OT status is unknown; do not
        # fabricate a regulation-time coach score.
        overtime = overtime_by_game.get(game_id)
        if overtime is None:
            continue
        candidates = logs.loc[logs["_game"].eq(game_id)]
        own = candidates.loc[candidates["_team"].eq(team)]
        opp = candidates.loc[candidates["_team"].eq(opponent)]
        if own.empty or opp.empty:
            continue
        own_points = pd.to_numeric(own["_pts"], errors="coerce").dropna().unique()
        opp_points = pd.to_numeric(opp["_pts"], errors="coerce").dropna().unique()
        if len(own_points) != 1 or len(opp_points) != 1:
            continue
        actual_coach_pdk = coach_points_from_game(
            float(own_points[0]), float(opp_points[0]), float(coach_cr), float(opp_cr), overtime
        )
        if not np.isfinite(actual_coach_pdk):
            continue
        rows.append({
            "coach": coach,
            "nba_game_id": game_id,
            "actual_coach_pdk": actual_coach_pdk,
            "team": team,
            "opponent": opponent,
            "team_final_points": float(own_points[0]),
            "opponent_final_points": float(opp_points[0]),
            "overtime": overtime,
        })
    actuals = pd.DataFrame(rows, columns=["coach", "nba_game_id", "actual_coach_pdk", "team", "opponent", "team_final_points", "opponent_final_points", "overtime"])
    if not actuals.empty:
        conflict = actuals.duplicated(["coach", "nba_game_id"], keep=False)
        if conflict.any():
            counts = actuals.loc[conflict].groupby(["coach", "nba_game_id"])["actual_coach_pdk"].nunique()
            if (counts > 1).any():
                raise ValueError("Conflicting coach scores for a coach-fixture pair.")
            actuals = actuals.drop_duplicates(["coach", "nba_game_id"], keep="last")
    expected_pairs = {
        (str(row["coach"]).strip(), str(row["nba_game_id"]).strip())
        for _, row in coach_market.iterrows()
        if str(row.get("coach", "")).strip() and str(row.get("nba_game_id", "")).strip() in fixture_ids
    }
    actual_pairs = set(zip(actuals["coach"].astype(str).str.strip(), actuals["nba_game_id"].astype(str).str.strip())) if not actuals.empty else set()
    return actuals, {
        "coach_market_rows": int(len(coach_market)),
        "expected_coach_fixture_pairs": len(expected_pairs),
        "mapped_coach_actual_rows": int(len(actual_pairs)),
        "mapped_fixtures_with_coach_actuals": int(actuals["nba_game_id"].nunique()) if not actuals.empty else 0,
        "expected_fixtures": int(len(fixtures)),
        "coverage": float(len(actual_pairs & expected_pairs) / len(expected_pairs)) if expected_pairs else 0.0,
        "missing_coach_fixture_pairs": [list(pair) for pair in sorted(expected_pairs - actual_pairs)[:50]],
        "overtime_inference_games": len(overtime_by_game),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Link official post-game Dunkest and NBA scores to a frozen pre-match run.")
    parser.add_argument("--data-dir", default="data", help="Data root for official outcomes and immutable result archives.")
    parser.add_argument("--run-id", help="Prediction run ID under data/predictions (or the name of --run-dir).")
    parser.add_argument("--run-dir", help="Explicit frozen prediction-run directory; supports isolated workspace runs without copying or modifying them.")
    parser.add_argument("--player-games", help="Official Dunkest per-player game history file; defaults to official_dunkest_player_games_<season>.parquet.")
    parser.add_argument("--team-logs", help="Final NBA team boxscore logs; defaults to team_game_logs_<season>.parquet.")
    parser.add_argument("--player-logs", help="Final NBA player boxscore logs used to infer overtime; defaults to player_game_logs_<season>.parquet.")
    parser.add_argument("--allow-partial", action="store_true", help="Archive partial outcomes for diagnosis; evaluator will report partial, never complete lineup metrics for missing players.")
    parser.add_argument("--output-dir", default="reports/backtest")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    run_dir = resolve_run_dir(data_dir, args.run_id, args.run_dir)
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_id = str(run_manifest.get("run_id", run_dir.name))
    config = run_manifest.get("configuration", {})
    season_id = str(config.get("season_id", ""))
    gameweek = int(config.get("target_gameweek", -1))
    season = str(config.get("season", ""))
    snapshot_dir = run_dir / "pre_match_snapshot"
    mapping_paths = sorted(snapshot_dir.glob(f"dunkest_fixture_mapping_{season_id}_*.parquet"))
    market_paths = sorted(snapshot_dir.glob(f"player_credits_{season_id}_gw{gameweek}.parquet"))
    coach_paths = sorted(snapshot_dir.glob(f"coach_market_{season_id}_gw{gameweek}.parquet"))
    if not mapping_paths or not market_paths or not coach_paths:
        raise ValueError("Frozen run is missing fixture mapping, player-credit market, or coach market snapshot.")
    processed = data_dir / "processed"
    player_path = Path(args.player_games).expanduser().resolve() if args.player_games else processed / f"official_dunkest_player_games_{season}.parquet"
    team_path = Path(args.team_logs).expanduser().resolve() if args.team_logs else processed / f"team_game_logs_{season}.parquet"
    nba_player_path = Path(args.player_logs).expanduser().resolve() if args.player_logs else processed / f"player_game_logs_{season}.parquet"
    mapping_all = pd.read_parquet(mapping_paths[0])
    fixtures, fixture_audit = prepare_fixture_index(mapping_all, gameweek)

    # Check the frozen fixture's safe retrieval cutoff before even statting or
    # hashing official post-game files. An early diagnostic must not consume
    # test actuals from disk or load them into memory.
    now = pd.Timestamp(datetime.now(timezone.utc))
    latest_kickoff = pd.to_datetime(fixtures["game_datetime_utc"], utc=True).max()
    safe_cutoff, timing_mode = safe_postgame_retrieval_cutoff(fixtures["game_datetime_utc"])
    timing_ok = now >= safe_cutoff
    out = Path(args.output_dir)
    if not timing_ok:
        out.mkdir(parents=True, exist_ok=True)
        collection_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        stem = f"post_match_collection_audit_{run_id}_{collection_id}"
        audit = {
            "status": "not_ready",
            "season_id": season_id,
            "gameweek": gameweek,
            "run_id": run_id,
            "collection_id": collection_id,
            "generated_at_utc": now.isoformat(),
            "source_files": {
                "official_player_games": str(player_path),
                "team_logs": str(team_path),
                "nba_player_logs_for_overtime": str(nba_player_path),
            },
            "source_file_fingerprints": {},
            "timing_check": {
                "passed": False,
                "latest_fixture_datetime_utc": latest_kickoff.isoformat(),
                "minimum_safe_retrieval_after_utc": safe_cutoff.isoformat(),
                "timing_mode": timing_mode,
            },
            "fixture_mapping": fixture_audit,
            "outcome_files_read": False,
            "outcome_access_skipped_reason": "before_safe_postgame_retrieval_cutoff",
        }
        missing_path = out / f"{stem}_missing.csv"
        audit_path = out / f"{stem}.json"
        pd.DataFrame(columns=["reason"]).to_csv(missing_path, index=False)
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "status": audit["status"],
            "audit": str(audit_path),
            "missing_rows": str(missing_path),
            "timing_check": False,
            "minimum_safe_retrieval_after_utc": safe_cutoff.isoformat(),
            "outcome_files_read": False,
        }, indent=2))
        return 2

    predictions, forecast_certification = validate_frozen_forecast(run_dir, run_manifest)

    source_paths = {
        "official_player_games": player_path,
        "team_logs": team_path,
        "nba_player_logs_for_overtime": nba_player_path,
        "frozen_run_manifest": run_dir / "manifest.json",
        "frozen_predictions": run_dir / Path(run_manifest["player_forecast_snapshot"]["path"]).name,
        "pre_lock_archive_manifest": run_dir / "archive_manifest.json",
        "pre_lock_registry": Path(forecast_certification["registry_path"]),
        "fixture_mapping": mapping_paths[0],
        "player_market": market_paths[0],
        "coach_market": coach_paths[0],
    }
    source_fingerprints_before = {
        name: fingerprint_file(path) for name, path in source_paths.items()
    }

    market = pd.read_parquet(market_paths[0])
    coach_market = pd.read_parquet(coach_paths[0])

    official_games = read_frame(player_path)
    team_logs = read_frame(team_path)
    nba_player_logs = read_frame(nba_player_path)
    players_actual, player_audit = build_player_outcome_panel(
        predictions, market, fixtures, official_games, nba_player_logs
    )
    evaluation = evaluate_player_forecast_panel(players_actual)
    coaches_actual, coach_audit = build_coach_actuals(coach_market, fixtures, team_logs, nba_player_logs)
    source_file_fingerprints = {
        name: fingerprint_file(path) for name, path in source_paths.items()
    }
    changed_sources = [
        name for name in source_paths
        if source_fingerprints_before[name]["sha256"]
        != source_file_fingerprints[name]["sha256"]
    ]
    if changed_sources:
        raise RuntimeError(
            "Collection inputs changed while actuals were being built; refusing to archive: "
            + ", ".join(changed_sources)
        )

    now = pd.Timestamp(datetime.now(timezone.utc))
    # Recheck at the end so a clock rollback during collection still fails closed.
    timing_ok = now >= safe_cutoff
    all_players_matched = bool(
        evaluation["candidate_count"] > 0
        and evaluation["minutes"]["n"] == evaluation["candidate_count"]
        and evaluation["pdk_official"]["n"] == evaluation["candidate_count"]
    )
    all_coaches_matched = coach_audit["coverage"] == 1.0
    ready = timing_ok and all_players_matched and all_coaches_matched
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    collection_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    stem = f"post_match_collection_audit_{run_id}_{collection_id}"
    audit = {
        "status": "ready_to_archive" if ready else "not_ready",
        "season_id": season_id,
        "gameweek": gameweek,
        "run_id": run_id,
        "collection_id": collection_id,
        "generated_at_utc": now.isoformat(),
        "source_files": {"official_player_games": str(player_path), "team_logs": str(team_path), "nba_player_logs_for_overtime": str(nba_player_path)},
        "source_file_fingerprints": source_file_fingerprints,
        "timing_check": {
            "passed": bool(timing_ok),
            "latest_fixture_datetime_utc": latest_kickoff.isoformat(),
            "minimum_safe_retrieval_after_utc": safe_cutoff.isoformat(),
            "timing_mode": timing_mode,
        },
        "fixture_mapping": fixture_audit,
        "pre_lock_certification": forecast_certification,
        "player_actuals": player_audit,
        "player_forecast_evaluation": evaluation,
        "coach_actuals": coach_audit,
        "missing_or_unresolved_player_rows": int(evaluation["missing_outcomes"] + evaluation["ambiguous_outcomes"]),
        "partial_archive_requested": bool(args.allow_partial),
    }
    if not timing_ok or (not ready and not args.allow_partial):
        players_actual.to_csv(out / f"{stem}_player_outcomes.csv", index=False)
        (out / f"{stem}_evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
        (out / f"{stem}_evaluation.md").write_text(
            _evaluation_markdown(evaluation, run_id, forecast_certification), encoding="utf-8"
        )
    if not timing_ok or (not ready and not args.allow_partial):
        (out / f"{stem}.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"status": audit["status"], "audit": str(out / f"{stem}.json"), "player_outcomes": str(out / f"{stem}_player_outcomes.csv"), "player_coverage": evaluation["outcome_coverage"], "coach_coverage": coach_audit["coverage"], "timing_check": timing_ok}, indent=2))
        return 2

    archive_settings = Settings(
        season=season,
        season_id=season_id,
        target_gameweek=gameweek,
        data_dir=str(data_dir),
    )
    idempotency_key = hashlib.sha256((
        f"{run_id}:{_canonical_frame_hash(players_actual, ['player_key', 'nba_game_id'])}:"
        f"{_canonical_frame_hash(coaches_actual, ['coach', 'nba_game_id'])}"
    ).encode("utf-8")).hexdigest()
    archive_dir = save_post_match_snapshot(
        archive_settings,
        gameweek,
        players_actual,
        coaches_actual,
        source=f"{player_path.name} + {team_path.name}; fixture-linked by {run_id}",
        metadata={
            "run_id": run_id,
            "collection_id": collection_id,
            "source_files": audit["source_files"],
            "source_file_fingerprints": source_file_fingerprints,
            "coverage_audit": {
                "player": player_audit,
                "coach": coach_audit,
                "evaluation": evaluation,
                "timing_check_passed": bool(timing_ok),
            },
            "idempotency_key": idempotency_key,
        },
    )
    audit["archive_dir"] = str(archive_dir)
    audit["status"] = "archived_complete" if ready else "archived_partial"
    (out / f"{stem}.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    players_actual.to_csv(out / f"{stem}_player_outcomes.csv", index=False)
    (out / f"{stem}_evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    (out / f"{stem}_evaluation.md").write_text(
        _evaluation_markdown(evaluation, run_id, forecast_certification), encoding="utf-8"
    )
    print(json.dumps({"status": audit["status"], "archive": str(archive_dir), "audit": str(out / f"{stem}.json"), "player_outcomes": str(out / f"{stem}_player_outcomes.csv"), "player_coverage": evaluation["outcome_coverage"], "coach_coverage": coach_audit["coverage"]}, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
