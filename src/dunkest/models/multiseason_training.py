"""Leakage-safe adapter for certified multi-season Dunkest PDK training rows.

The V3 dataset contains only valid Dunkest game labels from 2020/21 onward and
precomputed past-only NBA/Dunkest history features. Seasons 2018/19 and 2019/20
are intentionally not supervised targets because their Dunkest validity flags
were false; their verified NBA logs may still contribute to lagged history.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.features.pdk_history import PDK_HISTORY_FEATURES, pdk_history_features_for_rows
from dunkest.models.predictor import train_models

TRAIN_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25")
DEFAULT_DATASET = Path("processed/dunkest_pdk_game_training_2020-26_v3.parquet")
REQUIRED = {
    "season_label", "game_date", "gameId", "dunkest_player_id",
    "dunkest_player_name", "target_pdk", "history_games_before_target",
}


def _ratio(numerator: pd.Series, denominator: pd.Series, scale: float = 1.0) -> pd.Series:
    n = pd.to_numeric(numerator, errors="coerce")
    d = pd.to_numeric(denominator, errors="coerce")
    return (n * scale).div(d.where(d.gt(0)))


def adapt_certified_training_rows(
    source: pd.DataFrame,
    *,
    minimum_rows: int = 10_000,
    include_2025_26: bool = False,
    minutes_labels: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map only past-derived columns from the certified archive to production features."""
    missing = sorted(REQUIRED - set(source.columns))
    if missing:
        raise ValueError(f"Certified multi-season dataset is missing required columns: {missing}")
    allowed_seasons = TRAIN_SEASONS + (("2025-26",) if include_2025_26 else ())
    frame = source.loc[source["season_label"].astype(str).isin(allowed_seasons)].copy()
    if frame.empty:
        raise ValueError(f"No certified Dunkest PDK rows found for seasons {allowed_seasons}.")
    frame["GAME_DATE"] = pd.to_datetime(frame["game_date"], errors="coerce", utc=True).dt.tz_convert(None)
    frame["PLAYER_NAME"] = frame["dunkest_player_name"].astype("string")
    frame["PLAYER_ID"] = frame["dunkest_player_id"].astype("string")
    frame["GAME_ID"] = frame["gameId"].astype("string")
    frame["NBA_GAME_ID"] = frame.get("nba_GAME_ID", pd.Series(pd.NA, index=frame.index)).astype("string")
    frame["target_pdk_official"] = pd.to_numeric(frame["target_pdk"], errors="coerce")
    frame["expected_pdk_minutes_model"] = 0.0
    frame["is_inference"] = False
    frame["n_games"] = pd.to_numeric(
        frame.get("nba_history_games_before_target", frame["history_games_before_target"]),
        errors="coerce",
    ).fillna(0.0)
    # Modest, capped upweighting prevents the many veteran observations from
    # washing out first-five-game/rookie-like examples; weights never affect labels.
    history_count = pd.to_numeric(frame["history_games_before_target"], errors="coerce").fillna(0.0)
    frame["_training_sample_weight"] = np.select(
        [history_count.le(5), history_count.le(10)], [1.25, 1.10], default=1.0
    )
    frame["target_min"] = np.nan
    if (
        minutes_labels is not None
        and {"nba_GAME_ID", "nba_PLAYER_ID"}.issubset(frame.columns)
        and {"nba_GAME_ID", "nba_PLAYER_ID", "nba_MIN"}.issubset(minutes_labels.columns)
    ):
        minute_labels = minutes_labels.copy()
        minute_labels["nba_GAME_ID"] = minute_labels["nba_GAME_ID"].astype("string").str.strip()
        minute_labels["nba_PLAYER_ID"] = pd.to_numeric(minute_labels["nba_PLAYER_ID"], errors="coerce").astype("Int64")
        minute_labels["nba_MIN"] = pd.to_numeric(minute_labels["nba_MIN"], errors="coerce")
        if "nba_match_status" in minute_labels:
            minute_labels = minute_labels.loc[minute_labels["nba_match_status"].eq("matched_player_date_opponent")].copy()
        minute_labels = minute_labels.dropna(subset=["nba_GAME_ID", "nba_PLAYER_ID"])
        key = ["nba_GAME_ID", "nba_PLAYER_ID"]
        duplicate_labels = minute_labels.loc[minute_labels.duplicated(key, keep=False)]
        if not duplicate_labels.empty:
            conflicts = [
                identity for identity, group in duplicate_labels.groupby(key, dropna=False)
                if group["nba_MIN"].nunique(dropna=False) > 1
            ]
            if conflicts:
                raise ValueError(
                    f"Conflicting historical NBA minute labels for {len(conflicts)} game/player keys."
                )
        minute_labels = minute_labels.drop_duplicates(key, keep="first")
        frame["nba_GAME_ID"] = frame["nba_GAME_ID"].astype("string").str.strip()
        frame["nba_PLAYER_ID"] = pd.to_numeric(frame["nba_PLAYER_ID"], errors="coerce").astype("Int64")
        frame = frame.merge(
            minute_labels[key + ["nba_MIN"]].rename(columns={"nba_MIN": "_target_min_label"}),
            on=key,
            how="left",
            validate="many_to_one",
        )
        frame["target_min"] = pd.to_numeric(frame["_target_min_label"], errors="coerce")
        frame = frame.drop(columns=["_target_min_label"])

    if frame.duplicated(["season_label", "PLAYER_ID", "GAME_ID"]).any():
        raise ValueError("Certified multi-season training data contains duplicate season/player/game keys.")
    if frame.duplicated(["PLAYER_ID", "GAME_DATE"]).any():
        raise ValueError(
            "Certified multi-season PDK history has duplicate player/date rows; "
            "the four PDK history features cannot be ordered without leakage ambiguity."
        )
    pdk_history = pdk_history_features_for_rows(
        frame.assign(
            _pdk_history_player=frame["PLAYER_ID"],
            _pdk_history_season=frame["season_label"],
            _pdk_history_official=frame["target_pdk_official"],
            _pdk_history_minutes=frame["target_min"],
            _pdk_history_opponent=frame.get(
                "opponentTeamCode", pd.Series("", index=frame.index)
            ),
        ),
        group_col="_pdk_history_player",
        date_col="GAME_DATE",
        season_col="_pdk_history_season",
        official_col="_pdk_history_official",
        minutes_col="_pdk_history_minutes",
        opponent_col="_pdk_history_opponent",
    )
    for feature in PDK_HISTORY_FEATURES:
        frame[feature] = pd.to_numeric(pdk_history[feature], errors="coerce")

    # All mapped columns are lagged/expanding features in the V3 builder. No
    # same-game NBA box score, target score, or current-round outcome is exposed.
    mappings = {
        "pdk_mean_3": "prev3_pdk_mean",
        "pdk_mean_5": "prev5_pdk_mean",
        "pdk_mean_10": "prev10_pdk_mean",
        "pdk_std_5": "prev5_pdk_std",
        "min_mean_5": "prev5_nba_min_mean",
        "min_mean_3": "prev3_nba_min_mean",
        "pts_mean_5": "prev5_nba_pts_mean",
        "reb_mean_5": "prev5_nba_reb_mean",
        "ast_mean_5": "prev5_nba_ast_mean",
        "rest_days": "rest_days_from_nba_logs",
        "lag1_pdk": "lag1_pdk",
        "lag2_pdk": "lag2_pdk",
        "lag3_pdk": "lag3_pdk",
        "lag4_pdk": "lag4_pdk",
        "lag5_pdk": "lag5_pdk",
        "lag1_nba_min": "lag1_nba_min",
        "lag2_nba_min": "lag2_nba_min",
        "lag3_nba_min": "lag3_nba_min",
        "prev3_nba_min_mean": "prev3_nba_min_mean",
        "lag1_nba_pts": "lag1_nba_pts",
        "lag2_nba_pts": "lag2_nba_pts",
        "lag3_nba_pts": "lag3_nba_pts",
        "prev3_nba_pts_mean": "prev3_nba_pts_mean",
        "lag1_nba_reb": "lag1_nba_reb",
        "lag2_nba_reb": "lag2_nba_reb",
        "lag3_nba_reb": "lag3_nba_reb",
        "prev3_nba_reb_mean": "prev3_nba_reb_mean",
        "lag1_nba_ast": "lag1_nba_ast",
        "lag2_nba_ast": "lag2_nba_ast",
        "lag3_nba_ast": "lag3_nba_ast",
        "prev3_nba_ast_mean": "prev3_nba_ast_mean",
        "history_games_before_target": "history_games_before_target",
        "nba_history_games_before_target": "nba_history_games_before_target",
    }
    for target, source_col in mappings.items():
        frame[target] = pd.to_numeric(frame[source_col], errors="coerce") if source_col in frame else np.nan
    frame["pdk_trend_3v10"] = frame["prev3_pdk_mean"] - frame["prev10_pdk_mean"]
    frame["min_trend_3v5"] = frame["prev3_nba_min_mean"] - frame["prev5_nba_min_mean"]
    frame["min_last_vs_prev5"] = frame["lag1_nba_min"] - frame["prev5_nba_min_mean"]
    frame["abs_min_last_vs_prev5"] = pd.to_numeric(frame["min_last_vs_prev5"], errors="coerce").abs()

    # Derive target-team transition features using only earlier target-date rows.
    # The current team's identity is known for a historical game; prior team is shifted.
    if "nba_PLAYER_ID" in frame:
        frame["nba_PLAYER_ID"] = pd.to_numeric(frame["nba_PLAYER_ID"], errors="coerce").astype("Int64")
    else:
        frame["nba_PLAYER_ID"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    frame = frame.sort_values(["GAME_DATE", "nba_PLAYER_ID", "GAME_ID"], kind="stable").copy()
    team = frame.get("nba_TEAM_ABBREVIATION", pd.Series(pd.NA, index=frame.index)).astype("string").str.upper().str.strip()
    team = team.mask(team.isna() | team.isin(["", "<NA>", "NAN", "NONE"]))
    if frame["nba_PLAYER_ID"].notna().any():
        previous_team = team.groupby(frame["nba_PLAYER_ID"], dropna=True).shift(1)
        known_team = previous_team.notna() & team.notna()
        changed_team = known_team & previous_team.ne(team)
        frame["team_history_known"] = known_team.astype(float)
        frame["team_changed_from_previous_game"] = changed_team.astype(float)
        team_segment = changed_team.groupby(frame["nba_PLAYER_ID"], dropna=True).cumsum()
        frame["team_games_since_change"] = frame.groupby(["nba_PLAYER_ID", team_segment], dropna=True).cumcount().astype(float).reindex(frame.index).fillna(0.0)
        frame["min_std_5"] = frame.groupby("nba_PLAYER_ID", dropna=True)["target_min"].transform(
            lambda values: values.shift(1).rolling(5, min_periods=2).std(ddof=0)
        )
        frame["min_zero_rate_5"] = frame.groupby("nba_PLAYER_ID", dropna=True)["target_min"].transform(
            lambda values: values.shift(1).map(lambda value: float(value == 0) if pd.notna(value) else np.nan).rolling(5, min_periods=1).mean()
        )
    else:
        frame["team_history_known"] = 0.0
        frame["team_changed_from_previous_game"] = 0.0
        frame["team_games_since_change"] = 0.0
        frame["min_std_5"] = np.nan
        frame["min_zero_rate_5"] = np.nan

    lag_columns = [f"lag{i}_pdk" for i in range(1, 6)]
    if set(lag_columns).issubset(frame.columns):
        frame["pdk_median_5"] = frame[lag_columns].apply(pd.to_numeric, errors="coerce").median(axis=1)
    else:
        frame["pdk_median_5"] = np.nan
    for stat in ("stl", "blk", "tov", "oreb", "dreb", "fg3m", "fga", "fta"):
        source_col = f"prev5_nba_{stat}_mean"
        frame[f"{stat}_per36_5"] = _ratio(frame[source_col], frame["prev5_nba_min_mean"], 36.0) if source_col in frame else np.nan
    # The archive does not contain lagged 3PA, so FG3% is deliberately left
    # unavailable rather than approximated with all field-goal attempts.
    frame["fg3_pct_5"] = np.nan
    frame["ft_pct_5"] = _ratio(frame.get("prev5_nba_ftm_mean", pd.Series(np.nan, index=frame.index)), frame.get("prev5_nba_fta_mean", pd.Series(np.nan, index=frame.index)))
    frame["is_home"] = frame.get("opponentTeamPosition", pd.Series("", index=frame.index)).astype("string").str.casefold().eq("visitor").astype(float)
    frame["is_b2b"] = pd.to_numeric(frame["rest_days"], errors="coerce").le(1).astype(float)
    # Deliberately unavailable in the certified archive; these columns remain
    # NaN and are dropped by train_models instead of receiving invented values.
    for col in ("min_mean_10", "pdk_category_bonus_mean_5", "three_point_bonus_mean_5", "opp_pts_allowed_mean_5", "opp_plus_minus_mean_5", "opp_def_rating_mean_5", "opp_pace_mean_5", "opp_dreb_rate_mean_5"):
        frame[col] = np.nan
    frame["target_pdk"] = pd.to_numeric(frame["target_pdk"], errors="coerce")
    frame = frame.loc[
        frame["GAME_DATE"].notna()
        & frame["PLAYER_NAME"].notna()
        & frame["PLAYER_ID"].notna()
        & frame["GAME_ID"].notna()
        & np.isfinite(frame["target_pdk"].to_numpy(dtype=float, na_value=np.nan))
        & np.isfinite(frame["target_pdk_official"].to_numpy(dtype=float, na_value=np.nan))
    ].copy()
    if frame.duplicated(["season_label", "PLAYER_ID", "GAME_ID"]).any():
        raise ValueError("Certified multi-season training data contains duplicate season/player/game keys.")
    cutoff = pd.Timestamp("2026-07-01") if include_2025_26 else pd.Timestamp("2025-07-01")
    if frame["GAME_DATE"].max() >= cutoff:
        raise ValueError(f"Multi-season data exceeds the allowed cutoff {cutoff.date()}.")
    if len(frame) < minimum_rows:
        raise ValueError(f"Too few certified training rows after validation: {len(frame)}.")
    return frame.sort_values(["GAME_DATE", "PLAYER_ID", "GAME_ID"], kind="stable").reset_index(drop=True)


def _append_current_official_rows(
    historical: pd.DataFrame, current_features: pd.DataFrame, settings: Settings
) -> tuple[pd.DataFrame, int]:
    """Append only completed current-season rows with verified official PDK labels."""
    if current_features is None or current_features.empty:
        return historical.copy(), 0
    if not {"GAME_DATE", "target_pdk_official"}.issubset(current_features.columns):
        return historical.copy(), 0
    current = current_features.copy()
    current["GAME_DATE"] = pd.to_datetime(current["GAME_DATE"], errors="coerce", utc=True).dt.tz_convert(None)
    target = pd.to_numeric(current["target_pdk_official"], errors="coerce")
    inference = current.get("is_inference", pd.Series(False, index=current.index)).fillna(False).astype(bool)
    season_start = pd.to_datetime(settings.nba_season_start, errors="coerce")
    if pd.isna(season_start):
        raise ValueError(f"Invalid nba_season_start for current-season training: {settings.nba_season_start}")
    current = current.loc[
        ~inference
        & current["GAME_DATE"].notna()
        & current["GAME_DATE"].ge(season_start)
        & np.isfinite(target.to_numpy(dtype=float, na_value=np.nan))
    ].copy()
    if current.empty:
        return historical.copy(), 0
    current["target_pdk_official"] = pd.to_numeric(current["target_pdk_official"], errors="coerce")
    current["target_pdk"] = current["target_pdk_official"]
    current["expected_pdk_minutes_model"] = 0.0
    current["is_inference"] = False
    current["_training_sample_weight"] = 1.0

    # Only retain features supported by the certified historical adapter. A
    # current-only feature would be missing for every historical training row
    # and would create a season-specific shortcut from a tiny recent sample.
    from dunkest.models.predictor import FEATURE_COLS

    for column in FEATURE_COLS:
        if column not in historical or not np.isfinite(
            pd.to_numeric(historical[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        ).any():
            current[column] = np.nan
        elif column not in current:
            current[column] = np.nan
    key_columns = [column for column in ("PLAYER_ID", "GAME_ID") if column in current.columns]
    if len(key_columns) == 2 and current.duplicated(key_columns).any():
        raise ValueError("Current-season official PDK rows contain duplicate player/game identities.")
    combined = pd.concat([historical, current], ignore_index=True, sort=False)
    combined = combined.sort_values(["GAME_DATE", "PLAYER_ID", "GAME_ID"], kind="stable").reset_index(drop=True)
    return combined, int(len(current))


def train_multiseason_models(
    settings: Settings, current_features: pd.DataFrame | None = None
) -> tuple[dict, pd.DataFrame]:
    """Train on certified historical PDK and optional past-only current-season official labels.

    The 2025/26 historical holdout remains excluded. For an in-season forecast,
    only already-observed current-season games with official Dunkest PDK labels
    are appended; proxy labels and inference rows are never used.
    """
    path = settings.data_path / DEFAULT_DATASET
    if not path.exists():
        raise FileNotFoundError(
            f"Certified multi-season dataset is missing: {path}. "
            "Refusing to silently substitute an uncertified historical target."
        )
    source = pd.read_parquet(path)
    minute_labels_path = settings.data_path / "processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
    minute_labels = None
    if minute_labels_path.exists():
        minute_labels = pd.read_parquet(
            minute_labels_path,
            columns=["nba_GAME_ID", "nba_PLAYER_ID", "nba_MIN", "nba_match_status"],
        )
    historical = adapt_certified_training_rows(source, minutes_labels=minute_labels)
    training, current_rows = _append_current_official_rows(historical, current_features, settings)
    models, _ = train_models(
        settings,
        training,
        target_column="target_pdk_official",
        sample_weight=training["_training_sample_weight"],
    )
    models["_prediction_is_absolute"] = True
    models["_training_seasons"] = list(TRAIN_SEASONS) + ([settings.season] if current_rows else [])
    models["_training_dataset"] = str(path)
    models["_training_minute_labels_dataset"] = str(minute_labels_path) if minute_labels is not None else None
    models["_training_minute_labels_matched_rows"] = int(historical["target_min"].notna().sum())
    models["_training_label_certification"] = "verified_official_dunkest_pdk_valid_rows"
    models["_training_rows"] = int(len(training))
    models["_training_current_season_rows"] = int(current_rows)
    models["_training_date_min_utc"] = pd.Timestamp(training["GAME_DATE"].min()).isoformat()
    models["_training_date_max_utc"] = pd.Timestamp(training["GAME_DATE"].max()).isoformat()
    models["_rookie_policy"] = "history<=5 rows weight 1.25; history<=10 rows weight 1.10; current-season official labels weight 1.00; past-only features; fold-local imputation"
    return models, training
