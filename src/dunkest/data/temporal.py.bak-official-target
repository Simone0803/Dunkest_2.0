"""Contracts that keep pre-match inputs separate from post-match outcomes."""
from __future__ import annotations

import pandas as pd


class DataTiming:
    PRE_MATCH = "PRE_MATCH"
    POST_MATCH = "POST_MATCH"
    UNKNOWN = "UNKNOWN"


POST_MATCH_COLUMNS = {
    "target_pdk", "target_min", "actual_pdk", "pdk", "plus",
    "official_plusvalenza", "minutes", "min", "pts", "reb", "ast",
    "stl", "blk", "tov", "fgm", "fga", "ftm", "fta", "fg3m",
    "game_status_final", "final_score", "home_score", "away_score",
}


def validate_prematch_features(
    frame: pd.DataFrame,
    feature_columns: list[str] | tuple[str, ...],
    *,
    prediction_cutoff_column: str = "prediction_cutoff_utc",
    available_at_column: str = "available_at_utc",
) -> None:
    """Fail if selected columns are post-match or data arrived after cutoff."""
    forbidden = sorted({str(c).strip().lower() for c in feature_columns} & POST_MATCH_COLUMNS)
    if forbidden:
        raise ValueError(
            "POST_MATCH columns cannot be used as PRE_MATCH model features: "
            + ", ".join(forbidden)
        )
    if {prediction_cutoff_column, available_at_column}.issubset(frame.columns):
        cutoff = pd.to_datetime(frame[prediction_cutoff_column], errors="coerce", utc=True)
        available = pd.to_datetime(frame[available_at_column], errors="coerce", utc=True)
        invalid = cutoff.isna() | available.isna() | available.gt(cutoff)
        if invalid.any():
            raise ValueError(
                f"{int(invalid.sum())} PRE_MATCH feature row(s) have unknown or post-cutoff availability."
            )


def validate_player_fixture_associations(
    player_games: pd.DataFrame,
    fixtures: pd.DataFrame,
) -> pd.DataFrame:
    """Join player-game rows by official game ID and verify team/opponent sides."""
    player_required = {"nba_game_id", "team", "opponent", "home_away"}
    fixture_required = {"nba_game_id", "home_team", "away_team", "game_datetime_utc"}
    if not player_required.issubset(player_games.columns):
        raise ValueError(f"Player-game rows missing: {sorted(player_required - set(player_games.columns))}")
    if not fixture_required.issubset(fixtures.columns):
        raise ValueError(f"Fixtures missing: {sorted(fixture_required - set(fixtures.columns))}")
    if fixtures["nba_game_id"].duplicated().any():
        raise ValueError("Fixture identity nba_game_id must be unique within season.")
    fixture_columns = [
        column for column in (
            "nba_game_id", "home_team", "away_team", "game_datetime_utc",
            "source_retrieved_at_utc", "dunkest_gameweek", "dunkest_turn", "fantasy_eligible",
        ) if column in fixtures
    ]
    out = player_games.merge(fixtures[fixture_columns], on="nba_game_id", how="left", validate="many_to_one", indicator=True)
    if out["_merge"].ne("both").any():
        raise ValueError("One or more player-game rows have no fixture identity.")
    team = out["team"].astype(str).str.upper().str.strip()
    opponent = out["opponent"].astype(str).str.upper().str.strip()
    home = out["home_team"].astype(str).str.upper().str.strip()
    away = out["away_team"].astype(str).str.upper().str.strip()
    is_home = out["home_away"].astype(str).str.upper().str.strip().isin({"H", "HOME", "1", "TRUE"})
    correct = ((team.eq(home) & opponent.eq(away) & is_home) |
               (team.eq(away) & opponent.eq(home) & ~is_home))
    if not correct.all():
        raise ValueError(f"{int((~correct).sum())} player-game row(s) mismatch fixture team/opponent/home-away.")
    if {"home_team_eligible", "away_team_eligible"}.issubset(out.columns):
        home_eligible = out["home_team_eligible"].fillna(False).astype(bool)
        away_eligible = out["away_team_eligible"].fillna(False).astype(bool)
        player_eligible = (team.eq(home) & home_eligible) | (team.eq(away) & away_eligible)
        if not player_eligible.all():
            raise ValueError(
                f"{int((~player_eligible).sum())} player-game row(s) belong to a Dunkest non-valid/unknown team fixture."
            )
    if "game_datetime_utc" in player_games:
        player_time = pd.to_datetime(out["game_datetime_utc_x"], errors="coerce", utc=True)
        fixture_time = pd.to_datetime(out["game_datetime_utc_y"], errors="coerce", utc=True)
        if player_time.isna().any() or fixture_time.isna().any() or not player_time.eq(fixture_time).all():
            raise ValueError("Player-game datetime does not match the identified NBA fixture.")
        out = out.drop(columns=["game_datetime_utc_x", "game_datetime_utc_y"]).rename(
            columns={"game_datetime_utc": "player_game_datetime_utc"}
        )
    if "prediction_cutoff_utc" in out and "source_retrieved_at_utc" in out:
        cutoff = pd.to_datetime(out["prediction_cutoff_utc"], errors="coerce", utc=True)
        available = pd.to_datetime(out["source_retrieved_at_utc"], errors="coerce", utc=True)
        if cutoff.isna().any() or available.isna().any() or available.gt(cutoff).any():
            raise ValueError("Fixture mapping became available after the prediction cutoff.")
    return out.drop(columns="_merge")
