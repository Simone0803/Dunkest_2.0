from __future__ import annotations

import json
import warnings
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from dunkest.names import player_key

MODEL_FILENAME = "dunkest_pdk_historical_tuned_train_2020-25_test_2025-26_20261012_v1.joblib"
META_FILENAME = "dunkest_pdk_historical_tuned_train_2020-25_test_2025-26_20261012_v1.json"
TRAINING_FILENAME = "dunkest_pdk_game_training_2020-26_v3.parquet"
NBA_STAT_MAP = {
    "nba_min": "MIN", "nba_pts": "PTS", "nba_reb": "REB", "nba_ast": "AST",
    "nba_stl": "STL", "nba_blk": "BLK", "nba_tov": "TOV", "nba_fg3m": "FG3M",
    "nba_fga": "FGA", "nba_ftm": "FTM", "nba_oreb": "OREB", "nba_dreb": "DREB",
    "nba_plus_minus": "PLUS_MINUS",
}


def _normal_id(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text and text.lower() not in {"nan", "none", "<na>"} else None


def _date(value: object) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.NaT
    return parsed.tz_convert("UTC").tz_localize(None)


def _load_nba_history(data_path: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    historical_dir = data_path / "raw" / "nba_historical_logs_2018-25_v1"
    if historical_dir.exists():
        for path in sorted(historical_dir.glob("nba_player_game_logs_*.parquet")):
            df = pd.read_parquet(path)
            required = {"PLAYER_ID", "GAME_DATE"}
            if not required.issubset(df.columns):
                continue
            frames.append(df)
    current_path = data_path / "processed" / "player_game_logs_2025-26.parquet"
    if current_path.exists():
        df = pd.read_parquet(current_path)
        if {"PLAYER_ID", "GAME_DATE"}.issubset(df.columns):
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    history = pd.concat(frames, ignore_index=True, sort=False)
    history["PLAYER_ID"] = history["PLAYER_ID"].map(_normal_id)
    history["_date"] = pd.to_datetime(history["GAME_DATE"], errors="coerce", utc=True).dt.tz_convert("UTC").dt.tz_localize(None)
    history["_game_id"] = history.get("GAME_ID", pd.Series("", index=history.index)).astype(str)
    history = history.loc[history["PLAYER_ID"].notna() & history["_date"].notna()].copy()
    history = history.drop_duplicates(["PLAYER_ID", "_game_id", "_date"], keep="last")
    return history.sort_values(["PLAYER_ID", "_date", "_game_id"], kind="stable").reset_index(drop=True)


@lru_cache(maxsize=4)
def _load_bundle(data_dir: str):
    data_path = Path(data_dir)
    processed = data_path / "processed"
    model_path = processed / MODEL_FILENAME
    meta_path = processed / META_FILENAME
    training_path = processed / TRAINING_FILENAME
    if not all(path.exists() for path in (model_path, meta_path, training_path)):
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model = joblib.load(model_path)
    history = pd.read_parquet(training_path)
    required = {"season_id", "game_date", "dunkest_player_id", "dunkest_player_name", "target_pdk", "nba_player_id_history_map"}
    if not required.issubset(history.columns):
        return None
    history["season_id"] = history["season_id"].astype(str)
    history["game_date"] = pd.to_datetime(history["game_date"], errors="coerce", utc=True).dt.tz_convert("UTC").dt.tz_localize(None)
    history["dunkest_player_id"] = history["dunkest_player_id"].map(_normal_id)
    history["nba_player_id_history_map"] = history["nba_player_id_history_map"].map(_normal_id)
    history["target_pdk"] = pd.to_numeric(history["target_pdk"], errors="coerce")
    history = history.loc[history["game_date"].notna() & history["target_pdk"].notna()].copy()
    name_to_dunkest_id = (
        history.dropna(subset=["dunkest_player_id"])
        .assign(_name_key=lambda d: d["dunkest_player_name"].map(player_key))
        .sort_values("game_date")
        .drop_duplicates("_name_key", keep="last")
        .set_index("_name_key")["dunkest_player_id"].to_dict()
    )
    name_to_nba_id = (
        history.dropna(subset=["nba_player_id_history_map"])
        .assign(_name_key=lambda d: d["dunkest_player_name"].map(player_key))
        .sort_values("game_date")
        .drop_duplicates("_name_key", keep="last")
        .set_index("_name_key")["nba_player_id_history_map"].to_dict()
    )
    pdk_by_id = {
        player_id: group.sort_values("game_date")
        for player_id, group in history.dropna(subset=["dunkest_player_id"]).groupby("dunkest_player_id", sort=False)
    }
    nba = _load_nba_history(data_path)
    nba_by_id = {
        player_id: group.sort_values(["_date", "_game_id"], kind="stable")
        for player_id, group in nba.groupby("PLAYER_ID", sort=False)
    } if not nba.empty else {}
    nba_name_to_id: dict[str, str] = {}
    if not nba.empty and "PLAYER_NAME" in nba:
        names = nba.dropna(subset=["PLAYER_ID"]).copy()
        names["_name_key"] = names["PLAYER_NAME"].map(player_key)
        names = names.loc[names["_name_key"].ne("")].drop_duplicates("_name_key", keep="last")
        nba_name_to_id = names.set_index("_name_key")["PLAYER_ID"].to_dict()
    return model, meta, name_to_dunkest_id, name_to_nba_id, pdk_by_id, nba_by_id, nba_name_to_id


def _pdk_features(player_history: pd.DataFrame, target_date: pd.Timestamp) -> dict:
    prior = player_history.loc[player_history["game_date"].lt(target_date)] if not player_history.empty else player_history
    values = pd.to_numeric(prior["target_pdk"], errors="coerce").dropna().to_numpy(dtype=float) if not prior.empty else np.array([], dtype=float)
    out: dict[str, float] = {"history_games_before_target": float(len(values))}
    for lag in range(1, 6):
        out[f"lag{lag}_pdk"] = float(values[-lag]) if len(values) >= lag else np.nan
    for window in (3, 5, 10):
        tail = values[-window:]
        out[f"prev{window}_pdk_mean"] = float(np.mean(tail)) if len(tail) else np.nan
    tail5 = values[-5:]
    out["prev5_pdk_std"] = float(np.std(tail5, ddof=1)) if len(tail5) >= 2 else np.nan
    return out


def _nba_features(player_history: pd.DataFrame, target_date: pd.Timestamp) -> dict:
    prior = player_history.loc[player_history["_date"].lt(target_date)] if not player_history.empty else player_history
    out: dict[str, float] = {"nba_history_games_before_target": float(len(prior))}
    for alias, source in NBA_STAT_MAP.items():
        values = pd.to_numeric(prior[source], errors="coerce") if source in prior else pd.Series(dtype=float)
        clean = values.dropna().to_numpy(dtype=float)
        for lag in range(1, 4):
            out[f"lag{lag}_{alias}"] = float(clean[-lag]) if len(clean) >= lag else np.nan
        for window in (3, 5):
            tail = clean[-window:]
            out[f"prev{window}_{alias}_mean"] = float(np.mean(tail)) if len(tail) else np.nan
    if prior.empty:
        out["rest_days_from_nba_logs"] = np.nan
    else:
        last_date = prior["_date"].max()
        out["rest_days_from_nba_logs"] = float((target_date.normalize() - last_date.normalize()).days)
    return out


def predict_historical_pdk(
    data_path: Path,
    inference_features: pd.DataFrame,
    dunkest_players: pd.DataFrame,
    fallback_target_date: object | None = None,
) -> pd.DataFrame:
    """Predict game-level PDK using the tuned historical Extra Trees model.

    All feature histories are filtered strictly before each player's target date.
    Returns one row per market player; the caller decides whether to blend it.
    """
    bundle = _load_bundle(str(Path(data_path).resolve()))
    if bundle is None or inference_features.empty or dunkest_players.empty:
        return pd.DataFrame(columns=["player_name", "historical_rf_pdk", "historical_rf_pdk_games", "historical_rf_nba_games"])
    model, meta, name_to_dunkest_id, name_to_nba_id, pdk_by_id, nba_by_id, nba_name_to_id = bundle
    numeric_features = list(meta.get("numeric_features", []))
    categorical_features = list(meta.get("categorical_features", []))
    feature_columns = numeric_features + categorical_features
    feature_rows: list[dict] = []
    player_names: list[str] = []
    pdk_counts: list[int] = []
    nba_counts: list[int] = []
    latest_by_key = inference_features.copy()
    latest_by_key["_name_key"] = latest_by_key["PLAYER_NAME"].map(player_key)
    latest_by_key = latest_by_key.drop_duplicates("_name_key", keep="last").set_index("_name_key")
    fallback_date = _date(fallback_target_date) if fallback_target_date is not None else pd.NaT

    for _, market_row in dunkest_players.iterrows():
        name = str(market_row.get("player_name", "")).strip()
        key = player_key(name)
        if not key:
            continue
        feature_row = latest_by_key.loc[key] if key in latest_by_key.index else pd.Series(dtype=object)
        if isinstance(feature_row, pd.DataFrame):
            feature_row = feature_row.iloc[-1]
        target_date = _date(feature_row.get("NBA_GAME_DATETIME_UTC", pd.NaT))
        if pd.isna(target_date):
            target_date = _date(feature_row.get("GAME_DATE", pd.NaT))
        if pd.isna(target_date):
            target_date = fallback_date
        if pd.isna(target_date):
            target_date = pd.Timestamp("2100-01-01")
        dunkest_id = name_to_dunkest_id.get(key)
        nba_id = name_to_nba_id.get(key) or nba_name_to_id.get(key)
        pdk_history = pdk_by_id.get(dunkest_id, pd.DataFrame()) if dunkest_id else pd.DataFrame()
        nba_history = nba_by_id.get(nba_id, pd.DataFrame()) if nba_id else pd.DataFrame()
        row = _pdk_features(pdk_history, target_date)
        row.update(_nba_features(nba_history, target_date))
        opponent = feature_row.get("OPPONENT", "")
        row["opponentTeamCode"] = str(opponent).strip().upper() if pd.notna(opponent) else ""
        is_home = pd.to_numeric(feature_row.get("is_home", np.nan), errors="coerce")
        row["opponentTeamPosition"] = "visitor" if pd.notna(is_home) and float(is_home) >= 0.5 else "home" if pd.notna(is_home) else "unknown"
        for col in numeric_features:
            row.setdefault(col, np.nan)
        for col in categorical_features:
            row.setdefault(col, "unknown")
        feature_rows.append(row)
        player_names.append(name)
        pdk_counts.append(int(row.get("history_games_before_target", 0) or 0))
        nba_counts.append(int(row.get("nba_history_games_before_target", 0) or 0))

    if not feature_rows:
        return pd.DataFrame(columns=["player_name", "historical_rf_pdk", "historical_rf_pdk_games", "historical_rf_nba_games"])
    X = pd.DataFrame(feature_rows, columns=feature_columns)
    predictions = np.asarray(model.predict(X), dtype=float)
    predictions = np.clip(predictions, 0.0, None)
    return pd.DataFrame({
        "player_name": player_names,
        "historical_rf_pdk": predictions,
        "historical_rf_pdk_games": pdk_counts,
        "historical_rf_nba_games": nba_counts,
    })
