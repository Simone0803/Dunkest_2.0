from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.features.minutes import combine_minutes_and_pdk_per_min, expected_minutes_from_history
from dunkest.names import player_key

logger = logging.getLogger(__name__)


def _fixture_bool_series(series: pd.Series) -> pd.Series:
    """Parse fixture booleans conservatively; unknown source values are false."""
    def parse(value):
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if value is None or pd.isna(value):
            return False
        if isinstance(value, (int, np.integer)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            token = value.strip().casefold()
            if token in {"true", "1", "yes", "y", "on"}:
                return True
            if token in {"false", "0", "no", "n", "off"}:
                return False
        return False
    return series.map(parse).astype(bool)

def _to_naive_utc(series_or_value):
    """Normalize datetimes to tz-naive UTC so comparisons never mix tz-aware/naive."""
    values = pd.to_datetime(series_or_value, errors="coerce", utc=True)
    if isinstance(values, pd.Series):
        return values.dt.tz_convert("UTC").dt.tz_localize(None)
    if isinstance(values, pd.DatetimeIndex):
        return values.tz_convert("UTC").tz_localize(None)
    if pd.isna(values):
        return values
    if getattr(values, "tzinfo", None) is not None:
        return values.tz_convert("UTC").tz_localize(None)
    return values


def _validate_unique_player_game_dates(frame: pd.DataFrame) -> None:
    """Fail closed when date-only game logs cannot be ordered without leakage."""
    if frame.empty or "GAME_DATE" not in frame:
        return
    date = pd.to_datetime(frame["GAME_DATE"], errors="coerce", utc=True).dt.normalize()
    name_identity = frame.get("PLAYER_NAME", pd.Series("", index=frame.index)).map(player_key)
    name_identity = name_identity.replace("", pd.NA).map(
        lambda value: f"name:{value}" if pd.notna(value) else pd.NA
    )
    if "PLAYER_ID" in frame:
        player_id = frame["PLAYER_ID"].astype("string").str.strip()
        player_id = player_id.mask(player_id.str.casefold().isin(["", "<na>", "nan", "none"]))
        player_id = player_id.map(
            lambda value: f"id:{value}" if pd.notna(value) else pd.NA
        )
        identity = player_id.combine_first(name_identity)
    else:
        identity = name_identity
    valid = identity.notna() & date.notna()
    keys = pd.DataFrame({
        "identity": identity.loc[valid].to_numpy(),
        "date": date.loc[valid].to_numpy(),
    })
    duplicate = keys.duplicated(["identity", "date"], keep=False).to_numpy()
    if duplicate.any():
        bad = pd.DataFrame({
            "identity": identity[valid].to_numpy(),
            "date": date[valid].to_numpy(),
            "name": frame.loc[valid, "PLAYER_NAME"].astype(str).to_numpy()
                if "PLAYER_NAME" in frame else identity[valid].to_numpy(),
            "game_id": frame.loc[valid, "GAME_ID"].astype(str).to_numpy()
                if "GAME_ID" in frame else frame.loc[valid, "Game_ID"].astype(str).to_numpy()
                if "Game_ID" in frame else [""] * int(valid.sum()),
        })
        bad = bad.loc[duplicate].head(5)
        raise ValueError(
            "Player game logs contain duplicate player/date rows; date-only ordering "
            "would make shift(1) ambiguous. Deduplicate or provide trustworthy game timestamps. "
            f"Examples: {bad.to_dict(orient='records')}"
        )


def _pdk_feature_series(frame: pd.DataFrame) -> pd.Series:
    """Prefer verified official Dunkest scores for history; fall back to proxy PDK.

    Targets remain separate (target_pdk / target_pdk_official). This series
    is only used to construct lagged features, and all rolling operations shift
    it before aggregating so the current game's score cannot enter its features.
    """
    proxy = pd.to_numeric(
        frame.get("PDK", pd.Series(np.nan, index=frame.index)), errors="coerce"
    )
    if "PDK_OFFICIAL_VALID" not in frame:
        return proxy
    official = pd.to_numeric(frame["PDK_OFFICIAL_VALID"], errors="coerce")
    return official.combine_first(proxy)


def _empty_window_features(windows: list[int]) -> dict:
    feat: dict = {}
    for w in windows:
        feat[f"pdk_mean_{w}"] = np.nan
        feat[f"pdk_std_{w}"] = np.nan
        feat[f"pdk_median_{w}"] = np.nan
        feat[f"min_mean_{w}"] = np.nan
    feat["pdk_season_mean"] = np.nan
    feat["pdk_per_min_season"] = np.nan
    feat["pts_mean_5"] = np.nan
    feat["reb_mean_5"] = np.nan
    feat["ast_mean_5"] = np.nan
    for stat in ("STL", "BLK", "TOV", "OREB", "DREB", "FG3M", "FGA", "FTA"):
        feat[f"{stat.lower()}_per36_5"] = np.nan
    feat["fg3_pct_5"] = np.nan
    feat["ft_pct_5"] = np.nan
    feat["three_point_bonus_mean_5"] = np.nan
    feat["pdk_category_bonus_mean_5"] = np.nan
    for lag in range(1, 6):
        feat[f"lag{lag}_pdk"] = np.nan
    feat["pdk_trend_3v10"] = np.nan
    feat["min_trend_3v5"] = np.nan
    feat["min_last_vs_prev5"] = np.nan
    feat["abs_min_last_vs_prev5"] = np.nan
    feat["min_std_5"] = np.nan
    feat["min_zero_rate_5"] = np.nan
    feat["team_changed_from_previous_game"] = 0.0
    feat["team_history_known"] = 0.0
    feat["team_games_since_change"] = 0.0
    for lag in range(1, 4):
        for stat in ("min", "pts", "reb", "ast"):
            feat[f"lag{lag}_nba_{stat}"] = np.nan
    for stat in ("min", "pts", "reb", "ast"):
        feat[f"prev3_nba_{stat}_mean"] = np.nan
    feat["history_games_before_target"] = 0.0
    feat["nba_history_games_before_target"] = 0.0
    return feat


def _history_features(hist: pd.DataFrame, windows: list[int]) -> dict:
    feat = _empty_window_features(windows)
    if hist.empty:
        return feat
    pdk = _pdk_feature_series(hist)
    for lag in range(1, 6):
        feat[f"lag{lag}_pdk"] = float(pdk.iloc[-lag]) if len(pdk) >= lag and pd.notna(pdk.iloc[-lag]) else np.nan
    feat["pdk_trend_3v10"] = (feat.get("pdk_mean_3", np.nan) - feat.get("pdk_mean_10", np.nan))
    for stat, source_col in (("min", "MIN"), ("pts", "PTS"), ("reb", "REB"), ("ast", "AST")):
        values = pd.to_numeric(hist[source_col], errors="coerce") if source_col in hist else pd.Series(np.nan, index=hist.index)
        for lag in range(1, 4):
            feat[f"lag{lag}_nba_{stat}"] = float(values.iloc[-lag]) if len(values) >= lag and pd.notna(values.iloc[-lag]) else np.nan
        feat[f"prev3_nba_{stat}_mean"] = float(values.tail(3).mean()) if values.notna().any() else np.nan
    if "PDK_OFFICIAL_VALID" in hist:
        official_history = pd.to_numeric(hist["PDK_OFFICIAL_VALID"], errors="coerce")
        feat["history_games_before_target"] = float(official_history.notna().sum())
    else:
        feat["history_games_before_target"] = float(pdk.notna().sum())
    feat["nba_history_games_before_target"] = float(len(hist))
    for w in windows:
        tail = hist.tail(w)
        tail_pdk = pdk.tail(w)
        feat[f"pdk_mean_{w}"] = tail_pdk.mean()
        feat[f"pdk_std_{w}"] = tail_pdk.std(ddof=0)
        feat[f"pdk_median_{w}"] = tail_pdk.median()
        feat[f"min_mean_{w}"] = tail["MIN"].mean()
    feat["pdk_trend_3v10"] = feat.get("pdk_mean_3", np.nan) - feat.get("pdk_mean_10", np.nan)
    feat["min_trend_3v5"] = feat.get("prev3_nba_min_mean", np.nan) - feat.get("min_mean_5", np.nan)
    feat["min_last_vs_prev5"] = feat.get("lag1_nba_min", np.nan) - feat.get("min_mean_5", np.nan)
    feat["abs_min_last_vs_prev5"] = (
        abs(float(feat["min_last_vs_prev5"]))
        if pd.notna(feat["min_last_vs_prev5"]) else np.nan
    )
    recent_minutes = pd.to_numeric(hist.get("MIN", pd.Series(dtype=float)), errors="coerce").tail(5)
    feat["min_std_5"] = float(recent_minutes.std(ddof=0)) if recent_minutes.notna().sum() >= 2 else np.nan
    zero_flags = recent_minutes.map(lambda value: float(value == 0) if pd.notna(value) else np.nan)
    feat["min_zero_rate_5"] = float(zero_flags.mean()) if zero_flags.notna().any() else np.nan
    team_history = hist.get("TEAM_ABBREVIATION", pd.Series(dtype="string")).astype("string").str.upper().str.strip()
    team_history = team_history.mask(team_history.isna() | team_history.isin(["", "<NA>", "NAN", "NONE"]))
    valid_teams = team_history.dropna()
    if not valid_teams.empty:
        feat["team_history_known"] = float(len(valid_teams) >= 1)
        if len(valid_teams) >= 2:
            feat["team_changed_from_previous_game"] = float(valid_teams.iloc[-1] != valid_teams.iloc[-2])
        current_team = valid_teams.iloc[-1]
        streak = 0
        for prior_team in valid_teams.iloc[::-1]:
            if prior_team != current_team:
                break
            streak += 1
        feat["team_games_since_change"] = float(streak)
    feat["pdk_season_mean"] = pdk.mean()
    minutes = pd.to_numeric(hist["MIN"], errors="coerce")
    valid = minutes.gt(0) & pdk.notna()
    total_minutes = minutes.loc[valid].sum()
    feat["pdk_per_min_season"] = (
        float(pdk.loc[valid].sum() / total_minutes) if total_minutes > 0 else np.nan
    )
    feat["pts_mean_5"] = hist.tail(5)["PTS"].mean() if "PTS" in hist else np.nan
    feat["reb_mean_5"] = hist.tail(5)["REB"].mean() if "REB" in hist else np.nan
    feat["ast_mean_5"] = hist.tail(5)["AST"].mean() if "AST" in hist else np.nan
    tail = hist.tail(5)
    minutes = pd.to_numeric(tail.get("MIN", pd.Series(dtype=float)), errors="coerce")
    total_minutes = float(minutes.sum()) if not minutes.empty else 0.0
    if total_minutes > 0:
        for stat in ("STL", "BLK", "TOV", "OREB", "DREB", "FG3M", "FGA", "FTA"):
            if stat in tail:
                values = pd.to_numeric(tail[stat], errors="coerce")
                feat[f"{stat.lower()}_per36_5"] = float(values.sum() * 36.0 / total_minutes)
    for makes_col, attempts_col, feature in (
        ("FG3M", "FG3A", "fg3_pct_5"),
        ("FTM", "FTA", "ft_pct_5"),
    ):
        if makes_col in tail and attempts_col in tail:
            makes = pd.to_numeric(tail[makes_col], errors="coerce").sum()
            attempts = pd.to_numeric(tail[attempts_col], errors="coerce").sum()
            feat[feature] = float(makes / attempts) if attempts > 0 else np.nan
    if "FG3M" in tail:
        threes = pd.to_numeric(tail["FG3M"], errors="coerce")
        feat["three_point_bonus_mean_5"] = float(
            threes.map(lambda made: 5.0 if made >= 5 else 4.0 if made == 4 else 3.0 if made == 3 else 0.0).mean()
        )
    category_columns = {"PTS", "REB", "AST", "STL", "BLK"}
    if category_columns.issubset(tail.columns):
        categories = pd.DataFrame({
            column: pd.to_numeric(tail[column], errors="coerce")
            for column in category_columns
        }).ge(10).sum(axis=1)
        feat["pdk_category_bonus_mean_5"] = float(
            categories.map(lambda count: 50.0 if count >= 4 else 10.0 if count == 3 else 5.0 if count == 2 else 0.0).mean()
        )
    return feat


def _row_identity(row: pd.Series, extra: dict | None = None) -> dict:
    is_home = row.get("IS_HOME", np.nan)
    if pd.isna(is_home):
        matchup = str(row.get("MATCHUP", ""))
        is_home = True if " vs. " in matchup else False if " @ " in matchup else np.nan
    feat = {
        "PLAYER_NAME": row["PLAYER_NAME"],
        "GAME_DATE": row["GAME_DATE"],
        "NBA_GAME_ID": row.get("GAME_ID", row.get("Game_ID", pd.NA)),
        "NBA_GAME_DATETIME_UTC": row["GAME_DATE"],
        "OPPONENT": row.get("OPPONENT", ""),
        "TEAM_ABBREVIATION": row.get("TEAM_ABBREVIATION", ""),
        "is_home": float(is_home) if pd.notna(is_home) else np.nan,
        "target_pdk": row.get("PDK", np.nan),
        "target_pdk_official": row.get("PDK_OFFICIAL_VALID", np.nan),
        "target_min": row.get("MIN", np.nan),
        "is_inference": False,
        "n_games": np.nan,
    }
    if extra:
        feat.update(extra)
    return feat


def _normalize_player_opponents(
    player_logs: pd.DataFrame, team_logs: pd.DataFrame | None
) -> pd.DataFrame:
    """Repair opponent labels from the authoritative game/team rows when possible."""
    players = player_logs.copy()
    if "OPPONENT" not in players:
        players["OPPONENT"] = ""
    if team_logs is not None and not team_logs.empty:
        game_col = "Game_ID" if "Game_ID" in team_logs else "GAME_ID" if "GAME_ID" in team_logs else None
        player_game_col = "Game_ID" if "Game_ID" in players else "GAME_ID" if "GAME_ID" in players else None
        if game_col and player_game_col and "TEAM_ABBREVIATION" in team_logs and "TEAM_ABBREVIATION" in players:
            teams = team_logs[[game_col, "TEAM_ABBREVIATION", *(["MATCHUP"] if "MATCHUP" in team_logs else [])]].copy()
            teams["TEAM_ABBREVIATION"] = teams["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
            if "MATCHUP" in teams:
                teams["OPPONENT_CANONICAL"] = teams["MATCHUP"].astype(str).str.extract(
                    r"^\s*[A-Z]{2,3}\s+(?:vs\.|@)\s+([A-Z]{2,3})", expand=False
                ).str.upper()
            if "OPPONENT_CANONICAL" not in teams:
                teams["OPPONENT_CANONICAL"] = np.nan
            # Game IDs identify both teams even if a provider omits MATCHUP text.
            if teams["OPPONENT_CANONICAL"].isna().any():
                by_game = teams.groupby(game_col)["TEAM_ABBREVIATION"].agg(list)
                for idx in teams.index[teams["OPPONENT_CANONICAL"].isna()]:
                    members = by_game.get(teams.at[idx, game_col], [])
                    alternatives = [member for member in members if member != teams.at[idx, "TEAM_ABBREVIATION"]]
                    if alternatives:
                        teams.at[idx, "OPPONENT_CANONICAL"] = alternatives[0]
            keys = teams[[game_col, "TEAM_ABBREVIATION", "OPPONENT_CANONICAL"]].drop_duplicates(
                [game_col, "TEAM_ABBREVIATION"]
            )
            keys = keys.rename(columns={game_col: player_game_col, "TEAM_ABBREVIATION": "TEAM_ABBREVIATION"})
            players = players.drop(columns=["OPPONENT"], errors="ignore").merge(
                keys, on=[player_game_col, "TEAM_ABBREVIATION"], how="left"
            )
            players["OPPONENT"] = players["OPPONENT_CANONICAL"].fillna("")
            players = players.drop(columns="OPPONENT_CANONICAL")
    if "MATCHUP" in players:
        fallback = players["MATCHUP"].astype(str).str.extract(
            r"^\s*[A-Z]{2,3}\s+(?:vs\.|@)\s+([A-Z]{2,3})", expand=False
        ).str.upper()
        missing = players["OPPONENT"].astype(str).str.strip().eq("")
        players.loc[missing, "OPPONENT"] = fallback.loc[missing].fillna("")
    return players


def _player_opponent_features(hist: pd.DataFrame, opponent: object) -> tuple[float, float]:
    if hist.empty:
        return np.nan, 0.0
    minutes = pd.to_numeric(hist["MIN"], errors="coerce")
    pdk = _pdk_feature_series(hist)
    valid = minutes.gt(0) & pdk.notna()
    total_minutes = minutes.loc[valid].sum()
    if total_minutes <= 0:
        return np.nan, 0.0
    base_rate = float(pdk.loc[valid].sum() / total_minutes)
    if not str(opponent or "").strip() or "OPPONENT" not in hist:
        return base_rate, 0.0
    against = hist["OPPONENT"].astype(str).str.upper().str.strip().eq(
        str(opponent).strip().upper()
    ) & valid
    matchup_minutes = float(minutes.loc[against].sum())
    games = float(against.sum())
    if matchup_minutes <= 0:
        return base_rate, games
    matchup_pdk = float(pdk.loc[against].sum())
    shrink_minutes = 120.0
    shrunk_rate = (matchup_pdk + shrink_minutes * base_rate) / (matchup_minutes + shrink_minutes)
    return float(shrunk_rate), games


def _rolling_features(g: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    _validate_unique_player_game_dates(g)
    sort_columns = ["GAME_DATE"]
    if "GAME_ID" in g:
        sort_columns.append("GAME_ID")
    elif "Game_ID" in g:
        sort_columns.append("Game_ID")
    g = g.sort_values(sort_columns, kind="stable").reset_index(drop=True)
    count = len(g)
    player_names = g["PLAYER_NAME"]
    dates = g["GAME_DATE"]
    opponents = g.get("OPPONENT", pd.Series("", index=g.index)).astype(str).str.upper().str.strip()
    teams = g.get("TEAM_ABBREVIATION", pd.Series("", index=g.index))
    home = pd.to_numeric(
        g.get("IS_HOME", pd.Series(np.nan, index=g.index)), errors="coerce"
    )
    if "MATCHUP" in g:
        matchup = g["MATCHUP"].astype(str)
        home_fallback = pd.Series(
            np.select(
                [matchup.str.contains(" vs. "), matchup.str.contains(" @ ")],
                [1.0, 0.0],
                default=np.nan,
            ),
            index=g.index,
        )
        home = home.fillna(home_fallback)
    game_ids = g["GAME_ID"] if "GAME_ID" in g else g["Game_ID"] if "Game_ID" in g else pd.Series(pd.NA, index=g.index)
    out = pd.DataFrame(
        {
            "PLAYER_NAME": player_names,
            "GAME_DATE": dates,
            "NBA_GAME_ID": game_ids,
            "NBA_GAME_DATETIME_UTC": dates,
            "OPPONENT": g.get("OPPONENT", pd.Series("", index=g.index)),
            "TEAM_ABBREVIATION": teams,
            "is_home": home.astype(float),
            "target_pdk": g.get("PDK", pd.Series(np.nan, index=g.index)),
            "target_pdk_official": g.get(
                "PDK_OFFICIAL_VALID", pd.Series(np.nan, index=g.index)
            ),
            "target_min": g.get("MIN", pd.Series(np.nan, index=g.index)),
            "is_inference": False,
            "n_games": np.arange(count, dtype=float),
        }
    )

    def numeric(column: str) -> pd.Series:
        return pd.to_numeric(
            g[column] if column in g else pd.Series(np.nan, index=g.index),
            errors="coerce",
        )

    def rolling(column: str, window: int, operation: str) -> pd.Series:
        if window <= 0:
            return pd.Series(np.nan, index=g.index, dtype=float)
        source = _pdk_feature_series(g) if column == "PDK" else numeric(column)
        history = source.shift(1).rolling(window=window, min_periods=1)
        if operation == "mean":
            return history.mean()
        if operation == "std":
            return history.std(ddof=0)
        if operation == "median":
            return history.median()
        raise ValueError(f"Unsupported rolling operation: {operation}")

    pdk = _pdk_feature_series(g)
    minutes = numeric("MIN")
    for lag in range(1, 6):
        out[f"lag{lag}_pdk"] = pdk.shift(lag)
    for stat, source_col in (("min", "MIN"), ("pts", "PTS"), ("reb", "REB"), ("ast", "AST")):
        values = numeric(source_col)
        for lag in range(1, 4):
            out[f"lag{lag}_nba_{stat}"] = values.shift(lag)
        out[f"prev3_nba_{stat}_mean"] = values.shift(1).rolling(window=3, min_periods=1).mean()
    history_label = numeric("PDK_OFFICIAL_VALID") if "PDK_OFFICIAL_VALID" in g else pdk
    out["history_games_before_target"] = history_label.notna().astype(float).cumsum().shift(1).fillna(0.0)
    out["nba_history_games_before_target"] = np.arange(count, dtype=float)
    valid_pdk = minutes.gt(0) & pdk.notna()
    prior_minutes = minutes.where(valid_pdk, 0.0).cumsum().shift(1)
    prior_pdk = pdk.where(valid_pdk, 0.0).cumsum().shift(1)
    out["pdk_season_mean"] = pdk.expanding(min_periods=1).mean().shift(1)
    out["pdk_per_min_season"] = prior_pdk.div(prior_minutes.where(prior_minutes.gt(0)))

    for window in windows:
        out[f"pdk_mean_{window}"] = rolling("PDK", window, "mean")
        out[f"pdk_std_{window}"] = rolling("PDK", window, "std")
        out[f"pdk_median_{window}"] = rolling("PDK", window, "median")
        out[f"min_mean_{window}"] = rolling("MIN", window, "mean")
    out["pdk_trend_3v10"] = out.get("pdk_mean_3", pd.Series(np.nan,index=out.index)) - out.get("pdk_mean_10", pd.Series(np.nan,index=out.index))
    out["min_trend_3v5"] = out["prev3_nba_min_mean"] - out.get("min_mean_5", pd.Series(np.nan,index=out.index))
    out["min_last_vs_prev5"] = out["lag1_nba_min"] - out.get("min_mean_5", pd.Series(np.nan,index=out.index))
    out["abs_min_last_vs_prev5"] = out["min_last_vs_prev5"].abs()
    out["min_std_5"] = minutes.shift(1).rolling(window=5, min_periods=2).std(ddof=0)
    zero_flags = minutes.shift(1).map(lambda value: float(value == 0) if pd.notna(value) else np.nan)
    out["min_zero_rate_5"] = zero_flags.rolling(window=5, min_periods=1).mean()
    team_codes = teams.astype("string").str.upper().str.strip()
    team_codes = team_codes.mask(team_codes.isna() | team_codes.isin(["", "<NA>", "NAN", "NONE"]))
    previous_team = team_codes.shift(1)
    team_history_known = previous_team.notna() & team_codes.notna()
    team_changed = team_history_known & previous_team.ne(team_codes)
    out["team_history_known"] = team_history_known.astype(float)
    out["team_changed_from_previous_game"] = team_changed.astype(float)
    team_segment = team_changed.astype(int).cumsum()
    out["team_games_since_change"] = pd.Series(np.arange(count), index=out.index).groupby(team_segment).cumcount().astype(float)

    for column, feature in (("PTS", "pts_mean_5"), ("REB", "reb_mean_5"), ("AST", "ast_mean_5")):
        out[feature] = rolling(column, 5, "mean")

    recent_minutes = minutes.shift(1).rolling(window=5, min_periods=1).sum()
    for stat in ("STL", "BLK", "TOV", "OREB", "DREB", "FG3M", "FGA", "FTA"):
        values = numeric(stat).shift(1).rolling(window=5, min_periods=1).sum()
        rate = values.mul(36.0).div(recent_minutes.where(recent_minutes.gt(0)))
        out[f"{stat.lower()}_per36_5"] = rate

    for makes_col, attempts_col, feature in (
        ("FG3M", "FG3A", "fg3_pct_5"),
        ("FTM", "FTA", "ft_pct_5"),
    ):
        if makes_col in g and attempts_col in g:
            makes = numeric(makes_col).shift(1).rolling(window=5, min_periods=1).sum()
            attempts = numeric(attempts_col).shift(1).rolling(window=5, min_periods=1).sum()
            out[feature] = makes.div(attempts.where(attempts.gt(0)))
        else:
            out[feature] = np.nan

    threes = numeric("FG3M")
    three_point_bonus = pd.Series(
        np.select(
            [threes.ge(5), threes.eq(4), threes.eq(3)],
            [5.0, 4.0, 3.0],
            default=0.0,
        ),
        index=g.index,
    )
    out["three_point_bonus_mean_5"] = three_point_bonus.shift(1).rolling(
        window=5, min_periods=1
    ).mean()

    category_columns = {"PTS", "REB", "AST", "STL", "BLK"}
    if category_columns.issubset(g.columns):
        categories = pd.DataFrame(
            {column: numeric(column).ge(10) for column in category_columns},
            index=g.index,
        ).sum(axis=1)
        category_bonus = pd.Series(
            np.select(
                [categories.ge(4), categories.eq(3), categories.eq(2)],
                [50.0, 10.0, 5.0],
                default=0.0,
            ),
            index=g.index,
        )
        out["pdk_category_bonus_mean_5"] = category_bonus.shift(1).rolling(
            window=5, min_periods=1
        ).mean()
    else:
        out["pdk_category_bonus_mean_5"] = np.nan

    opponent_minutes = minutes.where(valid_pdk, 0.0).groupby(opponents, sort=False).cumsum()
    opponent_minutes = opponent_minutes.groupby(opponents, sort=False).shift(1)
    opponent_pdk = pdk.where(valid_pdk, 0.0).groupby(opponents, sort=False).cumsum()
    opponent_pdk = opponent_pdk.groupby(opponents, sort=False).shift(1)
    opponent_games = valid_pdk.astype(float).groupby(opponents, sort=False).cumsum()
    opponent_games = opponent_games.groupby(opponents, sort=False).shift(1).fillna(0.0)
    matchup_rate = (opponent_pdk + 120.0 * out["pdk_per_min_season"]).div(
        opponent_minutes + 120.0
    )
    has_opponent = opponents.str.strip().ne("")
    has_matchup_minutes = opponent_minutes.gt(0)
    out["player_opp_pdk_per_min"] = out["pdk_per_min_season"]
    out.loc[has_opponent & has_matchup_minutes, "player_opp_pdk_per_min"] = matchup_rate
    out["player_opp_games"] = opponent_games.where(has_opponent, 0.0)

    last = g.iloc[-1]
    inference_date = pd.Timestamp(last["GAME_DATE"]) + pd.Timedelta(days=1)
    next_row = _row_identity(
        last,
        extra={
            "GAME_DATE": inference_date,
            "NBA_GAME_ID": pd.NA,
            "NBA_GAME_DATETIME_UTC": pd.NaT,
            "OPPONENT": "",
            "target_pdk": np.nan,
            "target_pdk_official": np.nan,
            "target_min": np.nan,
            "is_inference": True,
            "n_games": float(len(g)),
        },
    )
    next_row.update(_history_features(g, windows))
    next_row["player_opp_pdk_per_min"], next_row["player_opp_games"] = _player_opponent_features(
        g, ""
    )
    return pd.concat([out, pd.DataFrame([next_row])], ignore_index=True)


def _pts_allowed(hist: pd.DataFrame) -> pd.Series | None:
    if hist.empty or "PTS" not in hist.columns:
        return None
    if "OPP_PTS" in hist.columns:
        return pd.to_numeric(hist["OPP_PTS"], errors="coerce")
    if "PLUS_MINUS" in hist.columns:
        return hist["PTS"] - hist["PLUS_MINUS"]
    if "PTS_ALLOWED" in hist.columns:
        return hist["PTS_ALLOWED"]
    return None


def _team_game_rates(team_logs: pd.DataFrame) -> pd.DataFrame:
    """Add box-score pace and efficiency rates, matched to each game's opponent."""
    df = team_logs.copy()
    if "Game_ID" not in df or "TEAM_ABBREVIATION" not in df:
        return df
    if "GAME_DATE" in df:
        df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df["GAME_ID"] = df["Game_ID"].astype(str)
    opponent_rows = df[["GAME_ID", "TEAM_ABBREVIATION", "PTS"]].copy()
    opponent_rows["OPPONENT"] = opponent_rows["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    opponent_rows = opponent_rows.rename(columns={"PTS": "OPP_PTS"}).drop(columns="TEAM_ABBREVIATION")
    df["OPPONENT"] = ""
    if "MATCHUP" in df:
        matchup = df["MATCHUP"].astype(str).str.extract(r"^\s*[A-Z]{2,3}\s+(?:vs\.|@)\s+([A-Z]{2,3})", expand=False)
        df["OPPONENT"] = matchup.fillna("").str.upper()
    # Game_ID is authoritative for points; matchup text supplies which side belongs to this row.
    df = df.merge(opponent_rows, on=["GAME_ID", "OPPONENT"], how="left")
    if "FGA" in df and "FTA" in df and "OREB" in df and "TOV" in df:
        df["EST_POSS"] = (
            pd.to_numeric(df["FGA"], errors="coerce")
            + 0.44 * pd.to_numeric(df["FTA"], errors="coerce")
            - pd.to_numeric(df["OREB"], errors="coerce")
            + pd.to_numeric(df["TOV"], errors="coerce")
        ).clip(lower=1.0)
    if "OPP_PTS" in df:
        # Find the opponent's estimated possessions from that opponent's game row.
        opp_possessions = df[["GAME_ID", "TEAM_ABBREVIATION", "EST_POSS"]].copy() if "EST_POSS" in df else None
        if opp_possessions is not None:
            opp_possessions["OPPONENT"] = opp_possessions["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
            opp_possessions = opp_possessions.rename(columns={"EST_POSS": "OPP_POSS"}).drop(columns="TEAM_ABBREVIATION")
            df = df.merge(opp_possessions, on=["GAME_ID", "OPPONENT"], how="left")
            df["GAME_PACE"] = (df["EST_POSS"] + df["OPP_POSS"]) / 2.0
            df["OFF_RATING"] = pd.to_numeric(df["PTS"], errors="coerce") * 100.0 / df["EST_POSS"]
            df["DEF_RATING"] = pd.to_numeric(df["OPP_PTS"], errors="coerce") * 100.0 / df["OPP_POSS"]
    if {"DREB", "OPPONENT"}.issubset(df.columns) and "OREB" in df:
        opp_rebounds = df[["GAME_ID", "TEAM_ABBREVIATION", "OREB"]].copy()
        opp_rebounds["OPPONENT"] = opp_rebounds["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
        opp_rebounds = opp_rebounds.rename(columns={"OREB": "OPP_OREB"}).drop(columns="TEAM_ABBREVIATION")
        df = df.merge(opp_rebounds, on=["GAME_ID", "OPPONENT"], how="left")
        denominator = pd.to_numeric(df["DREB"], errors="coerce") + pd.to_numeric(df["OPP_OREB"], errors="coerce")
        df["DREB_RATE"] = pd.to_numeric(df["DREB"], errors="coerce") / denominator.replace(0, np.nan)
    return df


def _team_context(team_logs: pd.DataFrame) -> pd.DataFrame:
    if team_logs.empty:
        return pd.DataFrame()
    df = _team_game_rates(team_logs)
    df = df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"])
    rows: list[dict] = []
    for team, g in df.groupby("TEAM_ABBREVIATION"):
        g = g.sort_values("GAME_DATE")
        for i in range(len(g)):
            hist = g.iloc[:i]
            row = g.iloc[i]
            allowed = _pts_allowed(hist)
            item = {
                "TEAM_ABBREVIATION": team,
                "GAME_DATE": row["GAME_DATE"],
                "team_pts_mean_5": hist.tail(5)["PTS"].mean() if len(hist) else np.nan,
                "team_pts_allowed_mean_5": allowed.tail(5).mean() if allowed is not None and len(hist) else np.nan,
                "team_plus_minus_mean_5": hist.tail(5)["PLUS_MINUS"].mean()
                if len(hist) and "PLUS_MINUS" in hist
                else np.nan,
                "team_def_rating_mean_5": hist.tail(5)["DEF_RATING"].mean() if "DEF_RATING" in hist else np.nan,
                "team_pace_mean_5": hist.tail(5)["GAME_PACE"].mean() if "GAME_PACE" in hist else np.nan,
                "team_dreb_rate_mean_5": hist.tail(5)["DREB_RATE"].mean() if "DREB_RATE" in hist else np.nan,
                "is_inference": False,
            }
            rows.append(item)
        if len(g):
            last = g.iloc[-1]
            hist = g
            allowed = _pts_allowed(hist)
            rows.append(
                {
                    "TEAM_ABBREVIATION": team,
                    "GAME_DATE": pd.Timestamp(last["GAME_DATE"]) + pd.Timedelta(days=1),
                    "team_pts_mean_5": hist.tail(5)["PTS"].mean(),
                    "team_pts_allowed_mean_5": allowed.tail(5).mean() if allowed is not None else np.nan,
                    "team_plus_minus_mean_5": hist.tail(5)["PLUS_MINUS"].mean()
                    if "PLUS_MINUS" in hist
                    else np.nan,
                    "team_def_rating_mean_5": hist.tail(5)["DEF_RATING"].mean() if "DEF_RATING" in hist else np.nan,
                    "team_pace_mean_5": hist.tail(5)["GAME_PACE"].mean() if "GAME_PACE" in hist else np.nan,
                    "team_dreb_rate_mean_5": hist.tail(5)["DREB_RATE"].mean() if "DREB_RATE" in hist else np.nan,
                    "is_inference": True,
                }
            )
    return pd.DataFrame(rows)


def _matchup_features(player_feats: pd.DataFrame, team_ctx: pd.DataFrame) -> pd.DataFrame:
    if team_ctx.empty:
        player_feats["opp_pts_allowed_mean_5"] = np.nan
        return player_feats
    opp_def = team_ctx.rename(
        columns={
            "TEAM_ABBREVIATION": "OPPONENT",
            "team_pts_mean_5": "opp_pts_mean_5",
            "team_pts_allowed_mean_5": "opp_pts_allowed_mean_5",
            "team_plus_minus_mean_5": "opp_plus_minus_mean_5",
            "team_def_rating_mean_5": "opp_def_rating_mean_5",
            "team_pace_mean_5": "opp_pace_mean_5",
            "team_dreb_rate_mean_5": "opp_dreb_rate_mean_5",
        }
    )
    keep = [
        c
        for c in (
            "OPPONENT",
            "GAME_DATE",
            "opp_pts_mean_5",
            "opp_pts_allowed_mean_5",
            "opp_plus_minus_mean_5",
            "opp_def_rating_mean_5",
            "opp_pace_mean_5",
            "opp_dreb_rate_mean_5",
        )
        if c in opp_def.columns
    ]
    merged = player_feats.merge(opp_def[keep], on=["OPPONENT", "GAME_DATE"], how="left")
    return merged


def _schedule_features(player_feats: pd.DataFrame) -> pd.DataFrame:
    df = player_feats.sort_values(["PLAYER_NAME", "GAME_DATE"]).copy()
    df["rest_days"] = df.groupby("PLAYER_NAME")["GAME_DATE"].diff().dt.days
    inference = df.get("is_inference", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    # Next-game / season-opener rows should not inherit last-season B2B flags.
    df.loc[inference, "rest_days"] = 3.0
    df["is_b2b"] = (df["rest_days"] <= 1).fillna(False).astype(int)
    df.loc[inference, "is_b2b"] = 0
    return df


def _attach_inference_team_transitions(
    features: pd.DataFrame,
    player_logs: pd.DataFrame,
    team_overrides: dict[str, str] | None,
) -> pd.DataFrame:
    """Attach target-team transition context using only the player's past logs.

    Current roster/team overrides are known at prediction time. They are compared
    with the last observed NBA team; no target-game result or future log is read.
    """
    if features.empty or "is_inference" not in features:
        return features
    out = features.copy()
    inference = out["is_inference"].fillna(False).astype(bool)
    if not inference.any():
        return out
    overrides = {
        player_key(name): str(team).strip().upper()
        for name, team in (team_overrides or {}).items()
        if str(team).strip()
    }
    logs_by_name = {
        name: group.sort_values("GAME_DATE", kind="stable")
        for name, group in player_logs.groupby("PLAYER_NAME", sort=False)
    } if {"PLAYER_NAME", "GAME_DATE"}.issubset(player_logs.columns) else {}
    for idx in out.index[inference]:
        name = str(out.at[idx, "PLAYER_NAME"])
        existing_team = out.at[idx, "TEAM_ABBREVIATION"]
        existing_team = "" if pd.isna(existing_team) else str(existing_team).strip().upper()
        target_team = overrides.get(player_key(name), existing_team)
        if target_team:
            out.at[idx, "TEAM_ABBREVIATION"] = target_team
        history = logs_by_name.get(name, pd.DataFrame())
        teams = (
            history.get("TEAM_ABBREVIATION", pd.Series(dtype="string"))
            .astype("string").str.upper().str.strip()
        )
        teams = teams.mask(teams.isna() | teams.isin(["", "<NA>", "NAN", "NONE"])).dropna()
        last_team = str(teams.iloc[-1]) if not teams.empty else ""
        known = bool(last_team)
        changed = bool(known and target_team and target_team != last_team)
        out.at[idx, "team_history_known"] = float(known)
        out.at[idx, "team_changed_from_previous_game"] = float(changed)
        if changed:
            out.at[idx, "team_games_since_change"] = 0.0
        elif known and target_team == last_team:
            streak = 0
            for prior_team in teams.iloc[::-1]:
                if prior_team != target_team:
                    break
                streak += 1
            out.at[idx, "team_games_since_change"] = float(streak)
        else:
            out.at[idx, "team_games_since_change"] = 0.0
    return out


def _attach_next_game_schedule(
    features: pd.DataFrame,
    schedule: pd.DataFrame | None,
    team_logs: pd.DataFrame | None,
    team_overrides: dict[str, str] | None,
    player_logs: pd.DataFrame,
    target_gameweek: int | None = None,
    include_completed_schedule: bool = False,
) -> pd.DataFrame:
    if schedule is None or schedule.empty:
        return features
    out = features.copy()
    schedule_rows = schedule.copy()
    # A configured Dunkest Giornata can only be resolved from an explicit
    # Dunkest bridge. NBA_WEEK_NUMBER is a different calendar namespace.
    if target_gameweek is not None:
        required_mapping = {
            "nba_game_id", "dunkest_gameweek", "dunkest_turn",
            "fantasy_eligible", "mapping_verified", "game_datetime_utc", "home_team", "away_team",
        }
        if not required_mapping.issubset(schedule_rows.columns):
            logger.warning(
                "No Dunkest fixture bridge for GW%s; NBA schedule matchup fields left unknown.",
                target_gameweek,
            )
            return out
        schedule_rows = schedule_rows.loc[
            pd.to_numeric(schedule_rows["dunkest_gameweek"], errors="coerce").eq(
                int(target_gameweek)
            )
            & _fixture_bool_series(schedule_rows["fantasy_eligible"])
            & _fixture_bool_series(schedule_rows["mapping_verified"])
        ].rename(
            columns={
                "game_datetime_utc": "GAME_DATE",
                "home_team": "HOME_TEAM",
                "away_team": "AWAY_TEAM",
                "nba_game_id": "NBA_GAME_ID",
                "dunkest_gameweek": "DUNKEST_GAMEWEEK",
                "dunkest_turn": "DUNKEST_TURN",
            }
        )
        schedule_rows["HOME_TEAM_ELIGIBLE"] = _fixture_bool_series(
            schedule_rows.get("home_team_eligible", schedule_rows["fantasy_eligible"])
        )
        schedule_rows["AWAY_TEAM_ELIGIBLE"] = _fixture_bool_series(
            schedule_rows.get("away_team_eligible", schedule_rows["fantasy_eligible"])
        )
        if schedule_rows.empty:
            logger.warning("No fantasy-eligible fixture mapping for Dunkest GW%s.", target_gameweek)
    elif "NBA_GAME_ID" not in schedule_rows and "GAME_ID" in schedule_rows:
        schedule_rows = schedule_rows.rename(columns={"GAME_ID": "NBA_GAME_ID"})
    if "HOME_TEAM_ELIGIBLE" not in schedule_rows:
        schedule_rows["HOME_TEAM_ELIGIBLE"] = True
    if "AWAY_TEAM_ELIGIBLE" not in schedule_rows:
        schedule_rows["AWAY_TEAM_ELIGIBLE"] = True
    required = {"GAME_DATE", "HOME_TEAM", "AWAY_TEAM"}
    if not required.issubset(schedule_rows.columns):
        return out
    schedule_rows["GAME_DATE"] = _to_naive_utc(schedule_rows["GAME_DATE"])
    schedule_rows["HOME_TEAM"] = schedule_rows["HOME_TEAM"].astype(str).str.upper().str.strip()
    schedule_rows["AWAY_TEAM"] = schedule_rows["AWAY_TEAM"].astype(str).str.upper().str.strip()
    schedule_rows = schedule_rows.dropna(subset=["GAME_DATE"]).sort_values("GAME_DATE")
    out["NBA_GAME_DATETIME_UTC"] = out.get(
        "NBA_GAME_DATETIME_UTC", pd.Series(pd.NaT, index=out.index)
    ).astype(object)
    if not include_completed_schedule and "GAME_STATUS" in schedule_rows:
        schedule_rows = schedule_rows.loc[
            pd.to_numeric(schedule_rows["GAME_STATUS"], errors="coerce").ne(3)
        ]
    inference = out.get("is_inference", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    prior_dates = (
        out.loc[~inference]
        .groupby("PLAYER_NAME")["GAME_DATE"]
        .max()
        .to_dict()
    )
    fixture_columns = [
        column for column in ("NBA_GAME_ID", "DUNKEST_GAMEWEEK", "DUNKEST_TURN")
        if column in schedule_rows
    ]
    home_games = schedule_rows.loc[schedule_rows["HOME_TEAM_ELIGIBLE"]].copy()
    home_games = home_games[["GAME_DATE", "HOME_TEAM", "AWAY_TEAM", *fixture_columns]].rename(
        columns={"HOME_TEAM": "TEAM", "AWAY_TEAM": "OPPONENT"}
    )
    home_games["IS_HOME"] = True
    away_games = schedule_rows.loc[schedule_rows["AWAY_TEAM_ELIGIBLE"]].copy()
    away_games = away_games[["GAME_DATE", "HOME_TEAM", "AWAY_TEAM", *fixture_columns]].rename(
        columns={"AWAY_TEAM": "TEAM", "HOME_TEAM": "OPPONENT"}
    )
    away_games["IS_HOME"] = False
    schedule_by_team = {
        team: group.sort_values("GAME_DATE")
        for team, group in pd.concat(
            [home_games, away_games], ignore_index=True
        ).groupby("TEAM", sort=False)
    }
    player_logs_by_name: dict[str, pd.DataFrame] = {}
    if not player_logs.empty and {"PLAYER_NAME", "GAME_DATE"}.issubset(player_logs.columns):
        dated_logs = player_logs.copy()
        dated_logs["_feature_date"] = _to_naive_utc(dated_logs["GAME_DATE"])
        player_logs_by_name = {
            name: group.sort_values("_feature_date")
            for name, group in dated_logs.groupby("PLAYER_NAME", sort=False)
        }
    overrides = {
        player_key(name): str(team).strip().upper()
        for name, team in (team_overrides or {}).items()
        if str(team).strip()
    }

    defense: dict[str, dict[str, float]] = {}
    if team_logs is not None and not team_logs.empty and "TEAM_ABBREVIATION" in team_logs:
        contexts = _team_context(team_logs)
        contexts = contexts.loc[contexts.get("is_inference", False).fillna(False)]
        for team, group in contexts.groupby("TEAM_ABBREVIATION"):
            latest = group.sort_values("GAME_DATE").iloc[-1]
            defense[str(team).upper()] = {
                "opp_pts_allowed_mean_5": float(latest.get("team_pts_allowed_mean_5", np.nan)),
                "opp_plus_minus_mean_5": float(latest.get("team_plus_minus_mean_5", np.nan)),
                "opp_def_rating_mean_5": float(latest.get("team_def_rating_mean_5", np.nan)),
                "opp_pace_mean_5": float(latest.get("team_pace_mean_5", np.nan)),
                "opp_dreb_rate_mean_5": float(latest.get("team_dreb_rate_mean_5", np.nan)),
            }

    for idx in out.index[inference]:
        player = str(out.at[idx, "PLAYER_NAME"])
        team = overrides.get(player_key(player), str(out.at[idx, "TEAM_ABBREVIATION"]).strip().upper())
        if team:
            out.at[idx, "TEAM_ABBREVIATION"] = team
        last_game = _to_naive_utc(prior_dates.get(player))
        if not team:
            continue
        team_games = schedule_by_team.get(team)
        if team_games is None:
            continue
        if pd.isna(last_game):
            game_index = 0
        else:
            game_index = team_games["GAME_DATE"].searchsorted(last_game, side="right")
        if game_index >= len(team_games):
            continue
        game = team_games.iloc[game_index]
        is_home = bool(game["IS_HOME"])
        opponent = game["OPPONENT"]
        if pd.isna(last_game):
            rest_days = 3.0
        else:
            rest_days = max(0, (game["GAME_DATE"].normalize() - last_game.normalize()).days)
        out.at[idx, "OPPONENT"] = opponent
        out.at[idx, "NBA_GAME_DATETIME_UTC"] = game["GAME_DATE"]
        for field in ("NBA_GAME_ID", "DUNKEST_GAMEWEEK", "DUNKEST_TURN"):
            if field in game:
                out.at[idx, field] = game[field]
        out.at[idx, "is_home"] = float(is_home)
        out.at[idx, "rest_days"] = float(rest_days)
        out.at[idx, "is_b2b"] = int(rest_days <= 1)
        player_history = player_logs_by_name.get(player, pd.DataFrame())
        if not player_history.empty:
            player_history = player_history.loc[
                player_history["_feature_date"].lt(game["GAME_DATE"])
            ]
        opp_rate, opp_games = _player_opponent_features(player_history, opponent)
        out.at[idx, "player_opp_pdk_per_min"] = opp_rate
        out.at[idx, "player_opp_games"] = opp_games
        for feature, value in defense.get(opponent, {}).items():
            out.at[idx, feature] = value
    return out


def _attach_current_season_form(
    features: pd.DataFrame,
    player_logs: pd.DataFrame,
    fallback_target_date: str | None = None,
) -> pd.DataFrame:
    """Attach as-of current/prior-season rates to inference rows only.

    The target season comes from the upcoming fixture date, not the last played
    game. This matters for season openers, when the latest historical game is
    still from the previous NBA season. Historical rows are strictly before the
    target timestamp; no current-game result can leak into the forecast.
    """
    if features.empty or player_logs.empty or "PLAYER_NAME" not in features:
        return features
    if "is_inference" not in features or not features["is_inference"].fillna(False).any():
        return features
    if not {"PLAYER_NAME", "GAME_DATE"}.issubset(player_logs.columns):
        return features

    out = features.copy()
    logs = player_logs.copy()
    logs["_season_date"] = _to_naive_utc(logs["GAME_DATE"])
    logs["_season_pdk"] = _pdk_feature_series(logs)
    logs["_season_minutes"] = pd.to_numeric(
        logs.get("MIN", pd.Series(np.nan, index=logs.index)), errors="coerce"
    )
    logs["_season_year"] = logs["_season_date"].dt.year - (
        logs["_season_date"].dt.month.lt(7).astype(int)
    )
    fallback = _to_naive_utc(fallback_target_date) if fallback_target_date else pd.NaT
    logs_by_player = {
        name: group for name, group in logs.groupby("PLAYER_NAME", sort=False)
    }

    for idx in out.index[out["is_inference"].fillna(False).astype(bool)]:
        player_name = out.at[idx, "PLAYER_NAME"]
        player_history = logs_by_player.get(player_name)
        history = player_history.copy() if player_history is not None else pd.DataFrame()
        if history.empty:
            out.at[idx, "pdk_per_min_current_season"] = np.nan
            out.at[idx, "current_season_games"] = 0.0
            out.at[idx, "pdk_per_min_prior_seasons"] = np.nan
            out.at[idx, "prior_seasons_games"] = 0.0
            continue

        target_date = _to_naive_utc(out.at[idx, "NBA_GAME_DATETIME_UTC"]) if (
            "NBA_GAME_DATETIME_UTC" in out and pd.notna(out.at[idx, "NBA_GAME_DATETIME_UTC"])
        ) else fallback
        if pd.isna(target_date):
            valid_dates = history["_season_date"].dropna()
            target_date = valid_dates.max() + pd.Timedelta(days=1) if not valid_dates.empty else pd.NaT
        if pd.isna(target_date):
            out.at[idx, "pdk_per_min_current_season"] = np.nan
            out.at[idx, "current_season_games"] = 0.0
            out.at[idx, "pdk_per_min_prior_seasons"] = np.nan
            out.at[idx, "prior_seasons_games"] = 0.0
            continue

        # The game log is post-match evidence; strict timestamp filtering is
        # essential even if the collector accidentally contains future rows.
        history = history.loc[history["_season_date"].lt(target_date)].copy()
        season_year = int(target_date.year - (target_date.month < 7))
        minutes = history["_season_minutes"]
        pdk = history["_season_pdk"]
        valid = minutes.gt(0) & pdk.notna() & minutes.notna()
        current = history["_season_year"].eq(season_year) & valid
        prior = history["_season_year"].lt(season_year) & valid

        current_minutes = float(minutes.loc[current].sum())
        current_points = float(pdk.loc[current].sum())
        prior_minutes = float(minutes.loc[prior].sum())
        prior_points = float(pdk.loc[prior].sum())
        out.at[idx, "pdk_per_min_current_season"] = (
            current_points / current_minutes if current_minutes > 0 else np.nan
        )
        out.at[idx, "current_season_games"] = float(current.sum())
        out.at[idx, "pdk_per_min_prior_seasons"] = (
            prior_points / prior_minutes if prior_minutes > 0 else np.nan
        )
        out.at[idx, "prior_seasons_games"] = float(prior.sum())
    return out

def build_feature_matrix(
    settings: Settings,
    player_logs: pd.DataFrame,
    team_logs: pd.DataFrame | None = None,
    injuries: pd.DataFrame | None = None,
    schedule: pd.DataFrame | None = None,
    team_overrides: dict[str, str] | None = None,
    target_gameweek: int | None = None,
    include_completed_schedule: bool = False,
) -> pd.DataFrame:
    if player_logs.empty:
        return pd.DataFrame()
    _validate_unique_player_game_dates(player_logs)
    player_logs = _normalize_player_opponents(player_logs, team_logs)
    windows = settings.rolling_windows
    parts = []
    for _, g in player_logs.groupby("PLAYER_NAME"):
        parts.append(_rolling_features(g, windows))
    feats = pd.concat(parts, ignore_index=True)

    if settings.use_schedule:
        feats = _schedule_features(feats)

    if settings.use_matchup and team_logs is not None:
        team_ctx = _team_context(team_logs)
        feats = _matchup_features(feats, team_ctx)

    if settings.use_injuries and injuries is not None and not injuries.empty:
        inj_count = len(injuries)
        feats["injury_list_size"] = inj_count

    minute_feats = expected_minutes_from_history(player_logs, windows)
    feats = combine_minutes_and_pdk_per_min(feats, minute_feats)
    feats = _attach_inference_team_transitions(feats, player_logs, team_overrides)
    feats = _attach_next_game_schedule(
        feats,
        schedule,
        team_logs,
        team_overrides,
        player_logs,
        target_gameweek=target_gameweek,
        include_completed_schedule=include_completed_schedule,
    )
    feats = _attach_current_season_form(
        feats, player_logs, fallback_target_date=settings.nba_season_start
    )
    if "is_inference" in feats.columns:
        feats["is_inference"] = feats["is_inference"].fillna(False).astype(bool)
    return feats
