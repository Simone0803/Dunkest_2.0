#!/usr/bin/env python3
"""Build v2 pregame features using the most recent NBA games, even if those games
were not marked Dunkest-valid. Official PDK lags remain based on valid PDK targets.
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
BASE_PATH = PROCESSED / "dunkest_pdk_game_training_2020-25_v1.parquet"
ENRICHED_PATH = PROCESSED / "dunkest_nba_player_games_enriched_2018-25_v1.parquet"
CROSSWALK_PATH = PROCESSED / "dunkest_nba_player_id_crosswalk_2018-25_v1.csv"
OUT_PATH = PROCESSED / "dunkest_pdk_game_training_2020-25_v2.parquet"
SCHEMA_PATH = PROCESSED / "dunkest_pdk_game_training_2020-25_v2_feature_schema.csv"
AUDIT_PATH = PROCESSED / "dunkest_pdk_game_training_2020-25_v2_build_audit.json"

SEASONS = [
    ("1", "2018-19"), ("3", "2019-20"), ("5", "2020-21"),
    ("7", "2021-22"), ("9", "2022-23"), ("13", "2023-24"),
    ("19", "2024-25"),
]
STAT_MAP = {
    "nba_min": "MIN",
    "nba_pts": "PTS",
    "nba_reb": "REB",
    "nba_ast": "AST",
    "nba_stl": "STL",
    "nba_blk": "BLK",
    "nba_tov": "TOV",
    "nba_fg3m": "FG3M",
    "nba_fga": "FGA",
    "nba_ftm": "FTM",
    "nba_oreb": "OREB",
    "nba_dreb": "DREB",
    "nba_plus_minus": "PLUS_MINUS",
}


def normalize_id(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text.isdigit() else None


def main() -> None:
    for path in (OUT_PATH, SCHEMA_PATH, AUDIT_PATH):
        if path.exists():
            raise SystemExit("Refusing to overwrite existing output: " + str(path))
    for path in (BASE_PATH, ENRICHED_PATH, CROSSWALK_PATH):
        if not path.exists():
            raise SystemExit("Missing source: " + str(path))

    base = pd.read_parquet(BASE_PATH).copy().reset_index(drop=True)
    base["dunkest_player_id"] = base["dunkest_player_id"].map(normalize_id)
    base["game_date"] = pd.to_datetime(base["game_date"], errors="coerce")
    if base["dunkest_player_id"].isna().any() or base["game_date"].isna().any():
        raise SystemExit("Null player ID or game date in v1 training candidates.")
    if base.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game keys in v1 training candidates.")

    crosswalk = pd.read_csv(CROSSWALK_PATH, dtype=str)
    if not crosswalk["crosswalk_unambiguous"].astype(str).str.lower().eq("true").all():
        raise SystemExit("Ambiguous Dunkest-to-NBA identity exists in crosswalk.")
    crosswalk["dunkest_player_id"] = crosswalk["dunkest_player_id"].map(normalize_id)
    crosswalk["nba_player_id_map"] = crosswalk["nba_player_ids"].map(normalize_id)
    player_map = crosswalk.set_index("dunkest_player_id")["nba_player_id_map"].to_dict()
    base["nba_player_id_history_map"] = base["dunkest_player_id"].map(player_map)
    no_identity = int(base["nba_player_id_history_map"].isna().sum())

    # Build complete NBA player-game history from every available regular season.
    nba_frames = []
    for season_id, season_label in SEASONS:
        path = NBA_DIR / f"nba_player_game_logs_{season_label}.parquet"
        if not path.exists():
            raise SystemExit("Missing NBA historical logs: " + str(path))
        df = pd.read_parquet(path).copy()
        df["PLAYER_ID"] = df["PLAYER_ID"].map(normalize_id)
        df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df["GAME_ID"] = df["GAME_ID"].astype(str)
        df["source_season_id"] = season_id
        df = df.loc[df["PLAYER_ID"].notna() & df["GAME_DATE"].notna()].copy()
        nba_frames.append(df)

    nba = pd.concat(nba_frames, ignore_index=True, sort=False)
    nba = nba.sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"], kind="stable").reset_index(drop=True)
    if nba.duplicated(["PLAYER_ID", "GAME_ID"]).any():
        raise SystemExit("Duplicate NBA player-game keys in historical NBA logs.")
    if nba.duplicated(["PLAYER_ID", "GAME_DATE"]).any():
        # A regular-season player should not have two games on one local date.
        duplicate_date_count = int(nba.duplicated(["PLAYER_ID", "GAME_DATE"], keep=False).sum())
    else:
        duplicate_date_count = 0

    history = pd.DataFrame({
        "nba_player_id_history_map": nba["PLAYER_ID"].astype(str),
        "history_nba_game_date": nba["GAME_DATE"],
        "history_nba_game_id": nba["GAME_ID"],
        "history_nba_season_id": nba["source_season_id"],
        "history_nba_game_number": nba.groupby("PLAYER_ID", sort=False).cumcount() + 1,
    })
    # For the last NBA game before the target date: current source row is lag 1,
    # shift(1) is lag 2, and so forth. Rolling windows include this preceding game.
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

    # merge_asof selects only NBA game dates strictly earlier than each Dunkest target.
    base["_row_id_v2"] = np.arange(len(base), dtype=np.int64)
    left = base[["_row_id_v2", "game_date", "nba_player_id_history_map"]].copy()
    left = left.sort_values(["game_date", "nba_player_id_history_map"], kind="stable")
    history = history.sort_values(
        ["history_nba_game_date", "nba_player_id_history_map"], kind="stable"
    )
    joined = pd.merge_asof(
        left,
        history,
        left_on="game_date",
        right_on="history_nba_game_date",
        by="nba_player_id_history_map",
        direction="backward",
        allow_exact_matches=False,
    )
    joined = joined.sort_values("_row_id_v2", kind="stable").reset_index(drop=True)
    if len(joined) != len(base):
        raise SystemExit("As-of join changed the training row count.")
    if joined["history_nba_game_date"].notna().any():
        bad_future = joined["history_nba_game_date"].notna() & joined["history_nba_game_date"].ge(joined["game_date"])
        if bad_future.any():
            raise SystemExit(f"Found {int(bad_future.sum())} non-past NBA history dates.")

    # Drop the v1 NBA features, replace with the latest previous NBA-game features.
    for alias in STAT_MAP:
        for col in (f"lag1_{alias}", f"lag2_{alias}", f"lag3_{alias}",
                    f"prev3_{alias}_mean", f"prev5_{alias}_mean"):
            if col in base:
                base = base.drop(columns=col)
            base[col] = joined[col].to_numpy()

    base["nba_history_games_before_target"] = pd.to_numeric(
        joined["history_nba_game_number"], errors="coerce"
    )
    base["rest_days_from_nba_logs"] = (
        base["game_date"] - pd.to_datetime(joined["history_nba_game_date"], errors="coerce")
    ).dt.days.astype("float64")
    base["prior_nba_history_game_date"] = pd.to_datetime(
        joined["history_nba_game_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    base["prior_nba_history_game_id"] = joined["history_nba_game_id"].astype("string")
    base["prior_nba_history_season_id"] = joined["history_nba_season_id"].astype("string")
    base = base.drop(columns="_row_id_v2")

    # The current target's matched NBA player identity must agree with the crosswalk.
    if "nba_PLAYER_ID" in base:
        current_id = base["nba_PLAYER_ID"].map(normalize_id)
        mapped_id = base["nba_player_id_history_map"].map(normalize_id)
        identity_conflicts = current_id.notna() & mapped_id.notna() & current_id.ne(mapped_id)
    else:
        identity_conflicts = pd.Series(False, index=base.index)
    if identity_conflicts.any():
        raise SystemExit(f"Crosswalk disagrees with current-game NBA match on {int(identity_conflicts.sum())} rows.")

    numeric_features = [
        "history_games_before_target",
        "lag1_pdk", "lag2_pdk", "lag3_pdk", "lag4_pdk", "lag5_pdk",
        "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean", "prev5_pdk_std",
        "nba_history_games_before_target", "rest_days_from_nba_logs",
    ]
    for alias in STAT_MAP:
        numeric_features.extend([
            f"lag1_{alias}", f"lag2_{alias}", f"lag3_{alias}",
            f"prev3_{alias}_mean", f"prev5_{alias}_mean",
        ])
    categorical_features = ["opponentTeamCode", "opponentTeamPosition"]
    safe_features = numeric_features + categorical_features
    if set(safe_features) - set(base.columns):
        raise SystemExit("Missing safe feature columns: " + str(sorted(set(safe_features)-set(base.columns))))
    forbidden = { "target_pdk", "pdk", "nba_PTS", "nba_REB", "nba_AST", "nba_MIN", "nba_GAME_ID", "nba_PLAYER_ID", "nba_match_status" }
    if forbidden.intersection(safe_features):
        raise SystemExit("Leakage column detected in safe features.")

    if base.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game keys after building v2.")
    base.to_parquet(OUT_PATH, index=False)
    schema = []
    for col in base.columns:
        if col == "target_pdk":
            role = "target"
            note = "Current-game official Dunkest PDK."
        elif col in categorical_features:
            role = "pre_game_feature"
            note = "Opponent/venue information known before tip-off."
        elif col in numeric_features:
            role = "pre_game_feature"
            note = "Lag/rolling values sourced strictly from games before target date."
        elif col in {"prior_nba_history_game_date", "prior_nba_history_game_id", "prior_nba_history_season_id", "nba_player_id_history_map"}:
            role = "audit_metadata"
            note = "Historical-source provenance; do not automatically pass as predictors."
        elif col in {"nba_GAME_ID", "nba_PLAYER_ID", "nba_TEAM_ABBREVIATION", "nba_match_status", "gameId", "dunkest_player_id"}:
            role = "identifier_or_audit"
            note = "Identifier/current-match diagnostic; keep out of numeric model inputs."
        else:
            role = "metadata"
            note = "Identifier/metadata; not on the curated safe-feature whitelist."
        schema.append({"column": col, "role": role, "safe_feature": col in safe_features, "notes": note})
    pd.DataFrame(schema).to_csv(SCHEMA_PATH, index=False)

    target_counts = base.groupby("season_id").size().to_dict()
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(OUT_PATH),
        "source_training_v1": str(BASE_PATH),
        "nba_history_source": str(NBA_DIR),
        "rows": len(base),
        "columns": len(base.columns),
        "safe_feature_count": len(safe_features),
        "safe_numeric_features": numeric_features,
        "safe_categorical_features": categorical_features,
        "rows_per_season_id": {str(k): int(v) for k,v in target_counts.items()},
        "dunkest_player_ids_without_nba_identity": no_identity,
        "rows_without_prior_nba_game": int(joined["history_nba_game_date"].isna().sum()),
        "rows_with_prior_nba_game": int(joined["history_nba_game_date"].notna().sum()),
        "rows_with_zero_or_negative_rest_days": int(base["rest_days_from_nba_logs"].le(0).fillna(False).sum()),
        "rows_with_nba_identity_conflict": int(identity_conflicts.sum()),
        "duplicate_player_dates_in_nba_logs": duplicate_date_count,
        "prior_nba_history_policy": "Most recent NBA game strictly before target date, including 2018/19 and 2019/20 regular-season boxscores; no same-date or current-game stats enter features.",
        "pdk_lag_policy": "PDK lag features still use only previous gameValidForDunkest=True labels; historical seasons 2018/19 and 2019/20 remain excluded from target-label history pending verification of the all-False validity flag.",
        "target_policy": "target_pdk uses current official per-game Dunkest PDK for rows gameValidForDunkest=True in season IDs 5, 7, 9, 13, 19.",
        "limitations": [
            "The model feature table is an experiment and does not modify production forecasts.",
            "Current-game boxscore fields in metadata are not on the safe-feature whitelist.",
            "NBA game IDs and Dunkest game IDs are different identifier namespaces; they are not equated.",
        ],
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== TRAINING DATASET V2 BUILT ===")
    print("rows",len(base),"columns",len(base.columns),"safe features",len(safe_features))
    print("rows per season",target_counts)
    print("without prior NBA game",audit["rows_without_prior_nba_game"])
    print("with zero/negative rest",audit["rows_with_zero_or_negative_rest_days"])
    print("NBA identity conflicts",audit["rows_with_nba_identity_conflict"])
    print("Outputs:",OUT_PATH,SCHEMA_PATH,AUDIT_PATH)


if __name__ == "__main__":
    main()
