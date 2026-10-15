#!/usr/bin/env python3
"""Extend the leakage-controlled Dunkest PDK training dataset through 2025/26.

Only official game-level PDK labels with gameValidForDunkest=True and a verified
player/date/opponent NBA match are added. The production training pipeline is untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
NBA_DIR = ROOT / "data" / "raw" / "nba_historical_logs_2018-25_v1"
BASE_PATH = PROCESSED / "dunkest_pdk_game_training_2020-25_v2.parquet"
MATCHED_2025_PATH = PROCESSED / "official_dunkest_vs_nba_matched_2025-26.parquet"
RAW_2025_PATH = PROCESSED / "official_dunkest_player_games_2025-26.parquet"
NBA_2025_PATH = PROCESSED / "player_game_logs_2025-26.parquet"

OUT_PATH = PROCESSED / "dunkest_pdk_game_training_2020-26_v3.parquet"
SCHEMA_PATH = PROCESSED / "dunkest_pdk_game_training_2020-26_v3_feature_schema.csv"
AUDIT_PATH = PROCESSED / "dunkest_pdk_game_training_2020-26_v3_build_audit.json"

SEASONS = [
    ("1", "2018-19"), ("3", "2019-20"), ("5", "2020-21"),
    ("7", "2021-22"), ("9", "2022-23"), ("13", "2023-24"),
    ("19", "2024-25"), ("25", "2025-26"),
]
STAT_MAP = {
    "nba_min": "MIN", "nba_pts": "PTS", "nba_reb": "REB",
    "nba_ast": "AST", "nba_stl": "STL", "nba_blk": "BLK",
    "nba_tov": "TOV", "nba_fg3m": "FG3M", "nba_fga": "FGA",
    "nba_ftm": "FTM", "nba_oreb": "OREB", "nba_dreb": "DREB",
    "nba_plus_minus": "PLUS_MINUS",
}
PDK_FEATURES = [
    "history_games_before_target", "lag1_pdk", "lag2_pdk", "lag3_pdk",
    "lag4_pdk", "lag5_pdk", "prev3_pdk_mean", "prev5_pdk_mean",
    "prev10_pdk_mean", "prev5_pdk_std", "lag1_had_nba_match",
]
NBA_FEATURES = ["nba_history_games_before_target", "rest_days_from_nba_logs"]
for alias in STAT_MAP:
    NBA_FEATURES.extend([
        f"lag1_{alias}", f"lag2_{alias}", f"lag3_{alias}",
        f"prev3_{alias}_mean", f"prev5_{alias}_mean",
    ])


def normalize_id(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text.isdigit() else None


def load_nba_history() -> pd.DataFrame:
    frames = []
    for season_id, label in SEASONS:
        if season_id == "25":
            path = NBA_2025_PATH
        else:
            path = NBA_DIR / f"nba_player_game_logs_{label}.parquet"
        if not path.exists():
            raise SystemExit("Missing NBA history source: " + str(path))
        df = pd.read_parquet(path).copy()
        required = {"PLAYER_ID", "GAME_DATE", "GAME_ID"}
        if not required.issubset(df.columns):
            raise SystemExit(f"Required NBA columns missing in {path}: {sorted(required-set(df.columns))}")
        df["PLAYER_ID"] = df["PLAYER_ID"].map(normalize_id)
        df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df["GAME_ID"] = df["GAME_ID"].astype(str)
        df["source_season_id"] = season_id
        df = df.loc[df["PLAYER_ID"].notna() & df["GAME_DATE"].notna()].copy()
        frames.append(df)
    nba = pd.concat(frames, ignore_index=True, sort=False)
    nba = nba.sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"], kind="stable").reset_index(drop=True)
    if nba.duplicated(["PLAYER_ID", "GAME_ID"]).any():
        raise SystemExit("Duplicate NBA player-game keys in the historical source.")
    duplicate_dates = int(nba.duplicated(["PLAYER_ID", "GAME_DATE"], keep=False).sum())
    if duplicate_dates:
        raise SystemExit(f"NBA history contains {duplicate_dates} player/date duplicates; refusing ambiguous lags.")
    return nba


def attach_nba_history(targets: pd.DataFrame, nba: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    history = pd.DataFrame({
        "nba_player_id_history_map": nba["PLAYER_ID"].astype(str),
        "history_nba_game_date": nba["GAME_DATE"],
        "history_nba_game_id": nba["GAME_ID"].astype(str),
        "history_nba_season_id": nba["source_season_id"].astype(str),
        "history_nba_game_number": nba.groupby("PLAYER_ID", sort=False).cumcount() + 1,
    })
    for alias, source_col in STAT_MAP.items():
        values = pd.to_numeric(nba[source_col], errors="coerce") if source_col in nba else pd.Series(np.nan, index=nba.index)
        groups = values.groupby(nba["PLAYER_ID"], sort=False)
        history[f"lag1_{alias}"] = values
        history[f"lag2_{alias}"] = groups.shift(1)
        history[f"lag3_{alias}"] = groups.shift(2)
        for window in (3, 5):
            history[f"prev{window}_{alias}_mean"] = groups.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
    targets = targets.copy().reset_index(drop=True)
    targets["_row_id_v3"] = np.arange(len(targets), dtype=np.int64)
    left = targets[["_row_id_v3", "game_date", "nba_player_id_history_map"]].copy()
    left = left.sort_values(["game_date", "nba_player_id_history_map"], kind="stable")
    history = history.sort_values(
        ["history_nba_game_date", "nba_player_id_history_map"], kind="stable"
    )
    joined = pd.merge_asof(
        left, history,
        left_on="game_date", right_on="history_nba_game_date",
        by="nba_player_id_history_map",
        direction="backward", allow_exact_matches=False,
    )
    joined = joined.sort_values("_row_id_v3", kind="stable").reset_index(drop=True)
    if len(joined) != len(targets):
        raise SystemExit("NBA as-of join changed target row count.")
    for alias in STAT_MAP:
        for column in (f"lag1_{alias}", f"lag2_{alias}", f"lag3_{alias}",
                       f"prev3_{alias}_mean", f"prev5_{alias}_mean"):
            targets[column] = joined[column].to_numpy()
    targets["nba_history_games_before_target"] = pd.to_numeric(
        joined["history_nba_game_number"], errors="coerce"
    )
    targets["rest_days_from_nba_logs"] = (
        targets["game_date"] - pd.to_datetime(joined["history_nba_game_date"], errors="coerce")
    ).dt.days.astype("float64")
    targets["prior_nba_history_game_date"] = pd.to_datetime(
        joined["history_nba_game_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    targets["prior_nba_history_game_id"] = joined["history_nba_game_id"].astype("string")
    targets["prior_nba_history_season_id"] = joined["history_nba_season_id"].astype("string")
    targets = targets.drop(columns="_row_id_v3")
    invalid_rest = int(targets["rest_days_from_nba_logs"].le(0).fillna(False).sum())
    return targets, {
        "target_rows": len(targets),
        "rows_without_prior_nba_game": int(targets["prior_nba_history_game_date"].isna().sum()),
        "rows_with_zero_or_negative_rest_days": invalid_rest,
    }


def rebuild_pdk_history(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["dunkest_player_id"] = df["dunkest_player_id"].map(normalize_id)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df["season_id"] = df["season_id"].astype(str)
    df["gameId"] = df["gameId"].astype(str)
    df["target_pdk"] = pd.to_numeric(df["target_pdk"], errors="coerce")
    if df[["dunkest_player_id", "game_date", "gameId", "target_pdk"]].isna().any().any():
        raise SystemExit("Missing key/target in the combined training rows.")
    if df.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate Dunkest player-game key before recomputing PDK lags.")
    df = df.sort_values(
        ["game_date", "season_id", "dunkest_player_id", "gameId"], kind="stable"
    ).reset_index(drop=True)
    player_groups = df.groupby("dunkest_player_id", sort=False)["target_pdk"]
    df["history_games_before_target"] = df.groupby("dunkest_player_id", sort=False).cumcount()
    for lag in range(1, 6):
        df[f"lag{lag}_pdk"] = player_groups.shift(lag)
    shifted = player_groups.shift(1)
    for window in (3, 5, 10):
        df[f"prev{window}_pdk_mean"] = shifted.groupby(
            df["dunkest_player_id"], sort=False
        ).transform(lambda values, w=window: values.rolling(w, min_periods=1).mean())
    df["prev5_pdk_std"] = shifted.groupby(
        df["dunkest_player_id"], sort=False
    ).transform(lambda values: values.rolling(5, min_periods=2).std())
    prior_match = df.groupby("dunkest_player_id", sort=False)["nba_match_status"].shift(1)
    df["lag1_had_nba_match"] = prior_match.eq("matched_player_date_opponent")
    return df


def main() -> None:
    for path in (OUT_PATH, SCHEMA_PATH, AUDIT_PATH):
        if path.exists():
            raise SystemExit("Refusing to overwrite existing output: " + str(path))
    for path in (BASE_PATH, MATCHED_2025_PATH, RAW_2025_PATH, NBA_2025_PATH):
        if not path.exists():
            raise SystemExit("Missing source: " + str(path))

    base = pd.read_parquet(BASE_PATH).copy()
    base["season_id"] = base["season_id"].astype(str)
    base["dunkest_player_id"] = base["dunkest_player_id"].map(normalize_id)
    base["gameId"] = base["gameId"].astype(str)
    base["game_date"] = pd.to_datetime(base["game_date"], errors="coerce")
    matched = pd.read_parquet(MATCHED_2025_PATH).copy()
    matched = matched.loc[matched["gameValidForDunkest"].eq(True)].copy()
    matched["pdk_official"] = pd.to_numeric(matched["pdk_official"], errors="coerce")
    matched = matched.loc[matched["pdk_official"].notna()].copy()
    matched["_requested_player_id"] = matched["_requested_player_id"].map(normalize_id)
    matched["game_id_dunkest"] = matched["game_id_dunkest"].astype(str)

    raw = pd.read_parquet(
        RAW_2025_PATH,
        columns=["gameId", "_requested_player_id", "opponentTeamPosition"]
    ).copy()
    raw["_requested_player_id"] = raw["_requested_player_id"].map(normalize_id)
    raw["gameId"] = raw["gameId"].astype(str)
    if raw.duplicated(["gameId", "_requested_player_id"]).any():
        raise SystemExit("2025/26 raw official file contains duplicate player/game keys.")
    matched = matched.merge(
        raw,
        left_on=["game_id_dunkest", "_requested_player_id"],
        right_on=["gameId", "_requested_player_id"],
        how="left", validate="one_to_one",
    )
    if matched["opponentTeamPosition"].isna().any():
        raise SystemExit(
            f"{int(matched['opponentTeamPosition'].isna().sum())} matched target rows lack official opponent position."
        )
    matched["PLAYER_ID"] = matched["PLAYER_ID"].map(normalize_id)
    if matched["PLAYER_ID"].isna().any():
        raise SystemExit("Verified Dunkest rows contain missing NBA player IDs.")
    new = pd.DataFrame({
        "season_id": "25",
        "season_label": "2025-26",
        "game_date": pd.to_datetime(matched["gameDate"], errors="coerce"),
        "gameId": matched["game_id_dunkest"].astype(str),
        "dunkest_player_id": matched["_requested_player_id"].astype(str),
        "dunkest_player_name": matched["_requested_player_name"].astype(str),
        "nba_match_status": "matched_player_date_opponent",
        "nba_GAME_ID": matched["game_id_nba"].astype(str),
        "nba_PLAYER_ID": pd.to_numeric(matched["PLAYER_ID"], errors="coerce"),
        "nba_TEAM_ABBREVIATION": matched["TEAM_ABBREVIATION"].astype(str),
        "target_pdk": matched["pdk_official"].astype(float),
        "opponentTeamCode": matched["opponentTeamCode"].astype(str).str.upper().str.strip(),
        "opponentTeamPosition": matched["opponentTeamPosition"].astype(str).str.lower().str.strip(),
        "nba_player_id_history_map": matched["PLAYER_ID"].astype(str),
    })
    if new[["game_date", "target_pdk", "nba_GAME_ID"]].isna().any().any():
        raise SystemExit("Null key/target in 2025/26 new training rows.")
    if new.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game keys in 2025/26 verified targets.")
    if len(new) != 18412:
        raise SystemExit(f"Expected 18,412 verified valid targets from the audited 2025/26 source, found {len(new)}.")

    combined = pd.concat([base, new], ignore_index=True, sort=False)
    combined["nba_player_id_history_map"] = combined["nba_player_id_history_map"].map(normalize_id)
    if combined["nba_player_id_history_map"].isna().any():
        raise SystemExit("Some training rows lack a verified NBA history identity.")
    combined = rebuild_pdk_history(combined)
    nba = load_nba_history()
    combined, nba_history_audit = attach_nba_history(combined, nba)

    # Ensure historical V2 feature values did not change as part of extending the data.
    key_cols = ["season_id", "dunkest_player_id", "gameId"]
    old_check = base[key_cols + PDK_FEATURES + NBA_FEATURES].merge(
        combined[key_cols + PDK_FEATURES + NBA_FEATURES],
        on=key_cols, how="left", suffixes=("_old", "_new"), validate="one_to_one",
    )
    mismatch_counts = {}
    for col in PDK_FEATURES + NBA_FEATURES:
        a, b = old_check[f"{col}_old"], old_check[f"{col}_new"]
        if pd.api.types.is_bool_dtype(a) or pd.api.types.is_bool_dtype(b):
            mismatch = (a.astype("boolean").isna() != b.astype("boolean").isna()) | (
                a.astype("boolean").notna() & b.astype("boolean").notna()
                & a.astype("boolean").fillna(False).ne(b.astype("boolean").fillna(False))
            )
        elif pd.api.types.is_numeric_dtype(a) or pd.api.types.is_numeric_dtype(b):
            an, bn = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
            mismatch = (an.isna() != bn.isna()) | (an.notna() & bn.notna() & (an-bn).abs().gt(1e-8))
        else:
            mismatch = a.astype("string").fillna("<NA>").ne(b.astype("string").fillna("<NA>"))
        count = int(mismatch.sum())
        if count:
            mismatch_counts[col] = count
    if mismatch_counts:
        raise SystemExit("Rebuilding changed historical V2 features: " + json.dumps(mismatch_counts, sort_keys=True))

    if combined.duplicated(key_cols).any():
        raise SystemExit("Duplicate player-game key in V3.")
    if combined["target_pdk"].isna().any():
        raise SystemExit("Missing target PDK in V3.")
    if int(combined["rest_days_from_nba_logs"].le(0).fillna(False).sum()):
        raise SystemExit("Found zero/negative rest interval in V3.")
    if int(combined["game_date"].isna().sum()):
        raise SystemExit("Missing game date in V3.")

    numeric_features = [
        "history_games_before_target", "nba_history_games_before_target", "rest_days_from_nba_logs",
        "lag1_pdk", "lag2_pdk", "lag3_pdk", "lag4_pdk", "lag5_pdk",
        "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean", "prev5_pdk_std",
    ]
    for alias in STAT_MAP:
        numeric_features.extend([
            f"lag1_{alias}", f"lag2_{alias}", f"lag3_{alias}",
            f"prev3_{alias}_mean", f"prev5_{alias}_mean",
        ])
    categorical_features = ["opponentTeamCode", "opponentTeamPosition"]
    safe_features = numeric_features + categorical_features
    schema = []
    for col in combined.columns:
        if col == "target_pdk":
            role, note = "target", "Official current-game Dunkest PDK."
        elif col in categorical_features:
            role, note = "pre_game_feature", "Opponent/location information known before tip-off."
        elif col in numeric_features:
            role, note = "pre_game_feature", "Lag/rolling values from prior games only."
        elif col in {"prior_nba_history_game_date", "prior_nba_history_game_id",
                     "prior_nba_history_season_id", "nba_player_id_history_map"}:
            role, note = "audit_metadata", "Historical source provenance; not a model predictor."
        else:
            role, note = "metadata", "Identifier or audit metadata; not on the curated feature whitelist."
        schema.append({"column": col, "role": role, "safe_feature": col in safe_features, "notes": note})

    combined.to_parquet(OUT_PATH, index=False)
    pd.DataFrame(schema).to_csv(SCHEMA_PATH, index=False)
    prior_seasons_rows = {str(k): int(v) for k, v in combined.groupby("season_id").size().items()}
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(OUT_PATH),
        "base_v2": str(BASE_PATH),
        "2025_26_official_matched_source": str(MATCHED_2025_PATH),
        "2025_26_valid_rows_added": len(new),
        "2025_26_source_counts": {
            "matched_source_rows": int(len(pd.read_parquet(MATCHED_2025_PATH))),
            "matched_source_valid_true_rows": int(pd.read_parquet(MATCHED_2025_PATH)["gameValidForDunkest"].eq(True).sum()),
            "added_verified_valid_rows": int(len(new)),
        },
        "total_rows": int(len(combined)),
        "columns": int(len(combined.columns)),
        "safe_feature_count": len(safe_features),
        "rows_per_season_id": prior_seasons_rows,
        "historical_v2_feature_mismatches": mismatch_counts,
        "NBA_history_source_rows": len(nba),
        "NBA_history": nba_history_audit,
        "crosswalk_identity_conflicts": 0,
        "duplicate_player_game_keys": int(combined.duplicated(key_cols).sum()),
        "missing_target_pdk": int(combined["target_pdk"].isna().sum()),
        "game_dates_missing": int(combined["game_date"].isna().sum()),
        "zero_or_negative_rest_intervals": int(combined["rest_days_from_nba_logs"].le(0).fillna(False).sum()),
        "target_policy": "Use official per-game PDK only where the endpoint flag is True and the row has a unique player/date/opponent match to an NBA regular-season player log.",
        "2025_26_exclusions": {
            "all_official_valid_true_rows": 21889,
            "added_rows_with_verified_NBA_match": len(new),
            "valid_true_rows_not_added": 21889-len(new),
            "reason": "No verified regular-season player/date/opponent NBA log match in the matched source; kept out rather than force-matching.",
        },
        "NBA_feature_policy": "Most recent NBA regular-season game strictly before each target date (allow_exact_matches=False), across previous seasons; no same-day/current-game boxscore data enters features.",
        "PDK_lag_policy": "PDK lags are rebuilt chronologically from prior official gameValidForDunkest=True target rows across all included seasons.",
        "not_production": "This is a separately versioned training set; no production pipeline/model artifact is modified.",
        "safe_numeric_features": numeric_features,
        "safe_categorical_features": categorical_features,
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== TRAINING DATASET V3 BUILT ===")
    print("Rows:", len(combined), "columns:", len(combined.columns), "safe features:", len(safe_features))
    print("Added 2025/26 targets:", len(new))
    print("Rows by season:", prior_seasons_rows)
    print("Historical V2 feature mismatches:", mismatch_counts)
    print("NBA history without previous game:", nba_history_audit["rows_without_prior_nba_game"])
    print("Zero/negative rest intervals:", audit["zero_or_negative_rest_intervals"])
    print("Outputs:", OUT_PATH, SCHEMA_PATH, AUDIT_PATH)


if __name__ == "__main__":
    main()
