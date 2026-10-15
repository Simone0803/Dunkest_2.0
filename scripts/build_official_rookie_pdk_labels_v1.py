#!/usr/bin/env python3
"""Build verified rookie-season Dunkest PDK/min labels from official game archives.

Only seasons with a verified official PDK target are used (2020-21 through 2025-26).
A player's first observed valid Dunkest season on/after their draft year is treated as
their observed debut season. Players with no verified appearance remain unlabeled.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dunkest.names import player_key

ROOT = Path(__file__).resolve().parents[1]
COLLEGE_PATH = ROOT / "data/rookie_college.csv"
TARGET_PATH = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
HISTORICAL_PATH = ROOT / "data/processed/official_dunkest_player_games_2018-25_v1.parquet"
CURRENT_PATH = ROOT / "data/processed/official_dunkest_player_games_2025-26.parquet"
OUTPUT_PATH = ROOT / "data/rookie_official_pdk.csv"
OUTPUT_COLUMNS = [
    "player_name", "player_key", "draft_year", "rookie_season_start",
    "official_dunkest_pdk_per_min", "official_dunkest_rookie_games",
    "official_dunkest_rookie_minutes", "official_dunkest_pdk_total",
    "label_source",
]


def build_labels() -> pd.DataFrame:
    college = pd.read_csv(COLLEGE_PATH)
    college["draft_year"] = pd.to_numeric(college["draft_year"], errors="coerce")
    college["player_key"] = college["player_name"].map(player_key)
    college = college.dropna(subset=["draft_year", "player_key"])
    if college.duplicated(["player_key", "draft_year"]).any():
        raise RuntimeError("Ambiguous college player identity within a draft class.")
    # Keep only draft cohorts covered by verified official PDK targets. This also
    # avoids same-name collisions with players drafted before the archive starts.
    college = college.loc[college["draft_year"].between(2020, 2025)].copy()
    if college["player_key"].duplicated().any():
        raise RuntimeError("Ambiguous player name across official-target draft cohorts.")

    target = pd.read_parquet(TARGET_PATH).copy()
    target["season_id"] = target["season_id"].astype(str)
    target["season_start"] = pd.to_numeric(target["season_label"].astype(str).str[:4], errors="coerce")
    target["gameId"] = target["gameId"].astype(str)
    target["dunkest_player_id"] = pd.to_numeric(target["dunkest_player_id"], errors="coerce")
    target["target_pdk"] = pd.to_numeric(target["target_pdk"], errors="coerce")
    target["player_key"] = target["dunkest_player_name"].map(player_key)
    target = target.dropna(subset=["season_start", "target_pdk", "player_key"])

    historical = pd.read_parquet(HISTORICAL_PATH).copy()
    historical["season_id"] = historical["season_id"].astype(str)
    historical["gameId"] = historical["gameId"].astype(str)
    historical["dunkest_player_id"] = pd.to_numeric(historical["dunkest_player_id"], errors="coerce")
    historical["min"] = pd.to_numeric(historical["min"], errors="coerce")
    valid = historical["gameValidForDunkest"].astype(str).str.lower().isin({"true", "1", "1.0"})
    historical = historical.loc[valid, ["season_id", "gameId", "dunkest_player_id", "min", "pdk"]]
    if historical.duplicated(["season_id", "gameId", "dunkest_player_id"]).any():
        raise RuntimeError("Historical official PDK/minute join keys are not unique.")

    old_target = target.loc[target["season_id"].ne("25")].copy()
    old = old_target.merge(
        historical,
        on=["season_id", "gameId", "dunkest_player_id"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_official"),
    )
    old["official_min"] = pd.to_numeric(old["min"], errors="coerce")
    old["official_pdk"] = pd.to_numeric(old["pdk"], errors="coerce")

    current_target = target.loc[target["season_id"].eq("25")].copy()
    current = pd.read_parquet(CURRENT_PATH).copy()
    current["gameId"] = current["gameId"].astype(str)
    current["player_key"] = current["_requested_player_name"].map(player_key)
    current["min"] = pd.to_numeric(current["min"], errors="coerce")
    current["pdk"] = pd.to_numeric(current["pdk"], errors="coerce")
    current = current[["gameId", "player_key", "min", "pdk"]]
    if current.duplicated(["gameId", "player_key"]).any():
        raise RuntimeError("Current-season official PDK/minute join keys are not unique.")
    new = current_target.merge(
        current,
        on=["gameId", "player_key"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_official"),
    )
    new["official_min"] = pd.to_numeric(new["min"], errors="coerce")
    new["official_pdk"] = pd.to_numeric(new["pdk"], errors="coerce")

    joined = pd.concat([old, new], ignore_index=True, sort=False)
    missing_minutes = int(joined["official_min"].isna().sum())
    if missing_minutes:
        raise RuntimeError(f"Official minutes missing for {missing_minutes} verified PDK rows.")
    score_diff = (joined["target_pdk"] - joined["official_pdk"]).abs()
    if score_diff.isna().any() or float(score_diff.max()) > 1e-8:
        raise RuntimeError("Official PDK targets disagree with the joined official game archive.")
    joined = joined.loc[joined["official_min"].gt(0)].copy()

    joined = joined.merge(
        college[["player_key", "draft_year", "player_name"]],
        on="player_key",
        how="inner",
        validate="many_to_one",
    )
    # Seasons 2018-19 and 2019-20 have unverified target flags and are excluded.
    # The official target set starts in 2020-21; earlier draft classes therefore
    # cannot have their true rookie-season target reconstructed from this archive.
    joined = joined.loc[
        joined["season_start"].ge(joined["draft_year"])
        & joined["draft_year"].between(2020, 2025)
    ].copy()
    first_season = (
        joined.groupby(["player_key", "draft_year"])["season_start"]
        .min()
        .rename("rookie_season_start")
        .reset_index()
    )
    joined = joined.merge(first_season, on=["player_key", "draft_year"], validate="many_to_one")
    joined = joined.loc[joined["season_start"].eq(joined["rookie_season_start"])].copy()

    labels = joined.groupby(
        ["player_key", "draft_year", "player_name", "rookie_season_start"], as_index=False
    ).agg(
        official_dunkest_pdk_total=("target_pdk", "sum"),
        official_dunkest_rookie_minutes=("official_min", "sum"),
        official_dunkest_rookie_games=("gameId", "nunique"),
    )
    labels["official_dunkest_pdk_per_min"] = (
        labels["official_dunkest_pdk_total"] / labels["official_dunkest_rookie_minutes"]
    )
    labels["label_source"] = "verified_official_dunkest_pdk_game_training_2020-26_v3"
    labels = labels[OUTPUT_COLUMNS].sort_values(["draft_year", "player_name"]).reset_index(drop=True)
    if labels.duplicated(["player_key", "draft_year"]).any():
        raise RuntimeError("Duplicate official rookie-season labels produced.")
    if labels["draft_year"].nunique() < 4 or len(labels) < 40:
        raise RuntimeError(f"Insufficient verified rookie labels: {len(labels)} rows.")
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing output.")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite {args.output}; pass --force to regenerate.")
    labels = build_labels()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(args.output, index=False, float_format="%.8f")
    print(f"Saved {args.output}: {len(labels)} labels from draft classes {sorted(labels.draft_year.unique())}")
    print(labels.groupby("draft_year").agg(
        players=("player_key", "size"),
        median_games=("official_dunkest_rookie_games", "median"),
        median_minutes=("official_dunkest_rookie_minutes", "median"),
        mean_pdk_per_min=("official_dunkest_pdk_per_min", "mean"),
    ).to_string())


if __name__ == "__main__":
    main()
