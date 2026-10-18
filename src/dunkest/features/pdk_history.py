"""Shared, official-only history definitions for the four PDK history features."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

OPPONENT_SHRINK_MINUTES = 120.0
PDK_HISTORY_FEATURES = (
    "pdk_season_mean",
    "pdk_per_min_season",
    "player_opp_pdk_per_min",
    "player_opp_games",
)


def season_key(value: object, game_date: object = None) -> int | None:
    """Return the starting year of an NBA season, deriving it from date if needed."""
    token = "" if value is None or pd.isna(value) else str(value)
    match = re.match(r"^\s*(\d{4})\s*[-/]\s*(?:\d{2}|\d{4})\s*$", token)
    if match:
        return int(match.group(1))
    date = pd.to_datetime(game_date, errors="coerce", utc=True)
    if pd.isna(date):
        return None
    return int(date.year - (date.month < 7))


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _opponent(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


class PdkHistoryAccumulator:
    """Past-only summaries using certified PDK and positive NBA minutes only.

    Each season is summarized separately. For a target season, use its prior
    official history when available; at its opener use the most recent earlier
    season with an official PDK label. Proxy PDK is intentionally never read.
    """

    def __init__(self) -> None:
        self._seasons: dict[int, dict[str, object]] = {}

    def add(
        self,
        season: int | None,
        official_pdk: object,
        minutes: object,
        opponent: object = None,
    ) -> None:
        score = _finite(official_pdk)
        if season is None or score is None:
            return
        state = self._seasons.setdefault(
            season,
            {"score_sum": 0.0, "score_count": 0, "pdk_sum": 0.0,
             "minutes_sum": 0.0, "opponents": {}},
        )
        state["score_sum"] = float(state["score_sum"]) + score
        state["score_count"] = int(state["score_count"]) + 1
        minute_value = _finite(minutes)
        if minute_value is None or minute_value <= 0:
            return
        state["pdk_sum"] = float(state["pdk_sum"]) + score
        state["minutes_sum"] = float(state["minutes_sum"]) + minute_value
        opponent_key = _opponent(opponent)
        if opponent_key:
            opponents = state["opponents"]
            opponent_state = opponents.setdefault(opponent_key, [0.0, 0.0, 0])
            opponent_state[0] += score
            opponent_state[1] += minute_value
            opponent_state[2] += 1

    def features(self, target_season: int | None, opponent: object = None) -> dict[str, float]:
        eligible = [
            season for season, state in self._seasons.items()
            if int(state["score_count"]) > 0
        ]
        if target_season is None:
            selected_season = max(eligible) if eligible else None
        elif int(self._seasons.get(target_season, {}).get("score_count", 0)) > 0:
            selected_season = target_season
        else:
            earlier = [season for season in eligible if season < target_season]
            selected_season = max(earlier) if earlier else None

        result = {name: np.nan for name in PDK_HISTORY_FEATURES}
        result["player_opp_games"] = 0.0
        if selected_season is None:
            return result

        state = self._seasons[selected_season]
        result["pdk_season_mean"] = float(state["score_sum"]) / int(state["score_count"])
        minutes_sum = float(state["minutes_sum"])
        base_rate = float(state["pdk_sum"]) / minutes_sum if minutes_sum > 0 else np.nan
        result["pdk_per_min_season"] = base_rate
        result["player_opp_pdk_per_min"] = base_rate
        opponent_key = _opponent(opponent)
        if opponent_key and np.isfinite(base_rate):
            opponent_state = state["opponents"].get(opponent_key)
            if opponent_state is not None:
                matchup_pdk, matchup_minutes, matchup_games = opponent_state
                result["player_opp_games"] = float(matchup_games)
                if matchup_minutes > 0:
                    result["player_opp_pdk_per_min"] = (
                        float(matchup_pdk) + OPPONENT_SHRINK_MINUTES * base_rate
                    ) / (float(matchup_minutes) + OPPONENT_SHRINK_MINUTES)
        return result


def summarize_pdk_history(
    history: pd.DataFrame,
    *,
    as_of: object = None,
    target_season: int | None = None,
    opponent: object = None,
    date_col: str = "GAME_DATE",
    season_col: str = "SEASON_YEAR",
    official_col: str = "PDK_OFFICIAL_VALID",
    minutes_col: str = "MIN",
    opponent_col: str = "OPPONENT",
) -> dict[str, float]:
    """Summarize rows strictly before the forecast; caller supplies past rows only."""
    accumulator = PdkHistoryAccumulator()
    if not history.empty:
        ordered = history.copy()
        if date_col in ordered:
            ordered[date_col] = pd.to_datetime(ordered[date_col], errors="coerce", utc=True)
            if as_of is not None:
                cutoff = pd.to_datetime(as_of, errors="coerce", utc=True)
                if pd.isna(cutoff):
                    raise ValueError(f"Invalid PDK history as-of timestamp: {as_of!r}")
                ordered = ordered.loc[ordered[date_col].lt(cutoff)]
            sort_columns = [date_col] + (["GAME_ID"] if "GAME_ID" in ordered else [])
            ordered = ordered.loc[ordered[date_col].notna()].sort_values(
                sort_columns, kind="stable"
            )
        for _, row in ordered.iterrows():
            season = season_key(row.get(season_col), row.get(date_col))
            accumulator.add(
                season,
                row.get(official_col),
                row.get(minutes_col),
                row.get(opponent_col),
            )
        if target_season is None and not ordered.empty:
            last = ordered.iloc[-1]
            target_season = season_key(last.get(season_col), last.get(date_col))
    return accumulator.features(target_season, opponent)


def pdk_history_features_for_rows(
    rows: pd.DataFrame,
    *,
    group_col: str,
    date_col: str,
    season_col: str,
    official_col: str,
    minutes_col: str,
    opponent_col: str,
) -> pd.DataFrame:
    """Build per-target features by accumulating only earlier rows per player."""
    values = np.full((len(rows), len(PDK_HISTORY_FEATURES)), np.nan, dtype=float)
    values[:, PDK_HISTORY_FEATURES.index("player_opp_games")] = 0.0
    working = rows.copy()
    working["_pdk_history_row_position"] = np.arange(len(working))
    for identity, group in working.groupby(group_col, sort=False, dropna=False):
        if identity is None or pd.isna(identity):
            continue
        normalized_dates = pd.to_datetime(group[date_col], errors="coerce", utc=True).dt.normalize()
        valid_dates = normalized_dates.dropna()
        if valid_dates.duplicated(keep=False).any():
            duplicate_dates = valid_dates.loc[valid_dates.duplicated(keep=False)].astype(str).tolist()[:5]
            raise ValueError(
                "PDK history contains duplicate player/date rows; temporal ordering "
                f"is ambiguous: {duplicate_dates}"
            )
        sort_columns = [date_col] + (["GAME_ID"] if "GAME_ID" in group else [])
        ordered = group.sort_values(sort_columns, kind="stable")
        accumulator = PdkHistoryAccumulator()
        for _, row in ordered.iterrows():
            game_date = pd.to_datetime(row.get(date_col), errors="coerce", utc=True)
            if pd.isna(game_date):
                continue
            season = season_key(row.get(season_col), row.get(date_col))
            position = int(row["_pdk_history_row_position"])
            feature_values = accumulator.features(season, row.get(opponent_col))
            values[position] = [feature_values[name] for name in PDK_HISTORY_FEATURES]
            accumulator.add(
                season,
                row.get(official_col),
                row.get(minutes_col),
                row.get(opponent_col),
            )
    return pd.DataFrame(values, index=rows.index, columns=PDK_HISTORY_FEATURES)
