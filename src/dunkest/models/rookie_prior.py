from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dunkest.names import player_key


MIN_HISTORY_ROWS = 40
MIN_DRAFT_CLASSES = 4
COLLEGE_PRIOR_BASE_WEIGHT = 0.20
COLLEGE_PRIOR_FADE_GAMES = 12.0
COLLEGE_MINUTES_BASE_WEIGHT = 0.15
MIN_CV_TRAIN_ROWS = 20
MIN_CV_VALIDATION_ROWS = 5
MIN_CV_FOLDS = 2
FULL_WEIGHT_RELATIVE_MAE_GAIN = 0.10

_NUMERIC_FEATURES = [
    "college_pdk_per_min",
    "points_per_40",
    "rebounds_per_40",
    "assists_per_40",
    "steals_per_40",
    "blocks_per_40",
    "turnovers_per_40",
    "usage",
    "starts_rate",
    "conference_strength",
    "offensive_rating",
    "defensive_rating",
    "college_pace",
    "age",
    "draft_pick",
    "log_college_games",
    "college_minutes_per_game",
]


def _number(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column in frame:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(default, index=frame.index, dtype=float)


def _rookie_sample_weights(minutes: pd.Series) -> pd.Series:
    positive = minutes[minutes.gt(0)]
    typical = positive.median()
    if pd.isna(typical) or typical <= 0:
        return pd.Series(1.0, index=minutes.index)
    return np.sqrt(
        (minutes.fillna(typical) / typical).clip(0.0625, 4.0)
    ).clip(0.25, 2.0)


def _college_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert per-game college box scores into pace-adjusted, per-40 features."""
    data = frame.copy()
    games = _number(data, "games")
    minutes = _number(data, "minutes_per_game")
    safe_minutes = minutes.where(minutes.gt(0))
    pace = _number(data, "pace", 70.0).fillna(70.0).clip(55.0, 90.0)
    pace_factor = (70.0 / pace).clip(0.80, 1.20)

    points = _number(data, "points_per_game", 0.0).fillna(0.0)
    rebounds = _number(data, "rebounds_per_game", 0.0).fillna(0.0)
    offensive_rebounds = _number(data, "offensive_rebounds_per_game", 0.0).fillna(0.0)
    assists = _number(data, "assists_per_game", 0.0).fillna(0.0)
    steals = _number(data, "steals_per_game", 0.0).fillna(0.0)
    blocks = _number(data, "blocks_per_game", 0.0).fillna(0.0)
    turnovers = _number(data, "turnovers_per_game", 0.0).fillna(0.0)
    fgm = _number(data, "field_goals_made_per_game", np.nan)
    fga = _number(data, "field_goals_attempted_per_game", np.nan)
    ftm = _number(data, "free_throws_made_per_game", np.nan)
    fta = _number(data, "free_throws_attempted_per_game", np.nan)
    missed_shots = (fga - fgm).clip(lower=0).fillna(0.0) + (fta - ftm).clip(lower=0).fillna(0.0)

    # Dunkest-like college box-score proxy. It deliberately omits NBA-specific
    # win, starter and multi-category bonuses; the historical NBA calibration
    # learns how much the proxy transfers to the pro game.
    college_pdk = (
        points + (rebounds + 0.25 * offensive_rebounds) + 1.5 * assists
        + 1.5 * steals + 1.5 * blocks - 1.5 * turnovers - missed_shots
    )
    threes = _number(data, "three_pointers_made_per_game", 0.0).fillna(0.0)
    college_pdk += np.select([threes.ge(5), threes.ge(4), threes.ge(3)], [5.0, 4.0, 3.0], default=0.0)
    per_minute = college_pdk.div(safe_minutes).replace([np.inf, -np.inf], np.nan)
    per_minute = per_minute * pace_factor

    feature_frame = pd.DataFrame(index=data.index)
    feature_frame["college_pdk_per_min"] = per_minute
    feature_frame["college_minutes_per_game"] = minutes
    for source, target in (
        (points, "points_per_40"), (rebounds, "rebounds_per_40"),
        (assists, "assists_per_40"), (steals, "steals_per_40"),
        (blocks, "blocks_per_40"), (turnovers, "turnovers_per_40"),
    ):
        feature_frame[target] = source.div(safe_minutes).mul(40.0).mul(pace_factor)
    feature_frame["usage"] = _number(data, "usage")
    starts = _number(data, "starts")
    feature_frame["starts_rate"] = starts.div(games.where(games.gt(0))).clip(0.0, 1.0)
    feature_frame["conference_strength"] = _number(data, "conference_strength")
    feature_frame["offensive_rating"] = _number(data, "offensive_rating")
    feature_frame["defensive_rating"] = _number(data, "defensive_rating")
    feature_frame["college_pace"] = pace
    feature_frame["age"] = _number(data, "age")
    feature_frame["draft_pick"] = _number(data, "draft_pick")
    feature_frame["log_college_games"] = np.log1p(games.clip(lower=0.0))
    for role in ("G", "F", "C"):
        feature_frame[f"position_{role}"] = (
            data.get("position", pd.Series("", index=data.index)).astype(str).str.upper().str[:1].eq(role).astype(float)
        )
    return feature_frame.replace([np.inf, -np.inf], np.nan)


def _historical_rookie_minutes_prior(
    raw: pd.DataFrame, features: pd.DataFrame, draft_years: pd.Series
) -> pd.DataFrame:
    """Predict conditional NBA rookie MPG, scored only on later draft classes.

    The role median is the temporal baseline. Feature imputation, scaling, and
    the baseline are fitted inside each draft-year fold. Current CR is not a
    training feature because historical Dunkest opening prices are unavailable
    for most cohorts; inference blends this prior conservatively with the
    current CR/lineup minutes estimate.
    """
    columns = [
        "player_name", "player_key", "college_projected_minutes_per_game",
        "college_minutes_prior_weight", "college_minutes_cv_mae",
        "college_minutes_baseline_cv_mae",
    ]
    games = _number(raw, "nba_rookie_games")
    total_minutes = _number(raw, "nba_rookie_minutes")
    target = total_minutes.div(games.where(games.gt(0))).replace([np.inf, -np.inf], np.nan)
    eligible = target.notna() & target.gt(0) & draft_years.notna()
    years = sorted(draft_years.loc[eligible].unique())
    if int(eligible.sum()) < MIN_HISTORY_ROWS or len(years) < MIN_DRAFT_CLASSES:
        return pd.DataFrame(columns=columns)

    requested = _NUMERIC_FEATURES + ["position_G", "position_F", "position_C"]
    actual: list[float] = []
    predicted: list[float] = []
    baseline: list[float] = []
    for split in range(2, len(years)):
        train_years = years[:split]
        validation_year = years[split]
        train_mask = eligible & draft_years.isin(train_years)
        validation_mask = eligible & draft_years.eq(validation_year)
        if int(train_mask.sum()) < MIN_CV_TRAIN_ROWS or int(validation_mask.sum()) < MIN_CV_VALIDATION_ROWS:
            continue
        train_x = features.loc[train_mask, requested]
        train_x = train_x.loc[:, train_x.notna().any(axis=0)]
        if train_x.empty:
            continue
        medians = train_x.median().fillna(0.0)
        model = make_pipeline(StandardScaler(), Ridge(alpha=20.0))
        model.fit(
            train_x.fillna(medians),
            target.loc[train_mask],
            ridge__sample_weight=np.sqrt(games.loc[train_mask].clip(lower=1.0)).to_numpy(dtype=float),
        )
        validation_x = features.loc[validation_mask, train_x.columns].fillna(medians)
        predicted.extend(np.clip(model.predict(validation_x), 0.0, 40.0).tolist())
        actual.extend(target.loc[validation_mask].tolist())

        train_roles = raw.loc[train_mask, "position"].astype(str).str.upper().str[:1]
        validation_roles = raw.loc[validation_mask, "position"].astype(str).str.upper().str[:1]
        role_medians = target.loc[train_mask].groupby(train_roles).median()
        baseline.extend(
            validation_roles.map(role_medians).fillna(float(target.loc[train_mask].median())).tolist()
        )

    if len(actual) < MIN_CV_VALIDATION_ROWS * MIN_CV_FOLDS:
        return pd.DataFrame(columns=columns)
    cv_mae = float(np.mean(np.abs(np.asarray(actual) - np.asarray(predicted))))
    baseline_mae = float(np.mean(np.abs(np.asarray(actual) - np.asarray(baseline))))
    relative_gain = (baseline_mae - cv_mae) / max(baseline_mae, 1e-9)
    weight = COLLEGE_MINUTES_BASE_WEIGHT * float(
        np.clip(relative_gain / FULL_WEIGHT_RELATIVE_MAE_GAIN, 0.0, 1.0)
    )

    current_year = draft_years.max()
    candidates = (
        target.isna()
        & draft_years.eq(current_year)
        & features["college_minutes_per_game"].notna()
    )
    if not candidates.any():
        return pd.DataFrame(columns=columns)

    train_x = features.loc[eligible, requested]
    train_x = train_x.loc[:, train_x.notna().any(axis=0)]
    if train_x.empty:
        return pd.DataFrame(columns=columns)
    medians = train_x.median().fillna(0.0)
    model = make_pipeline(StandardScaler(), Ridge(alpha=20.0))
    model.fit(
        train_x.fillna(medians),
        target.loc[eligible],
        ridge__sample_weight=np.sqrt(games.loc[eligible].clip(lower=1.0)).to_numpy(dtype=float),
    )
    current_x = features.loc[candidates, train_x.columns].fillna(medians)
    return pd.DataFrame(
        {
            "player_name": raw.loc[candidates, "player_name"].astype(str).values,
            "college_projected_minutes_per_game": np.clip(model.predict(current_x), 0.0, 40.0),
            "college_minutes_prior_weight": weight,
            "college_minutes_cv_mae": cv_mae,
            "college_minutes_baseline_cv_mae": baseline_mae,
        }
    ).assign(
        player_key=lambda frame: frame["player_name"].map(player_key)
    )[columns].drop_duplicates("player_key", keep="last").reset_index(drop=True)


def load_college_rookie_priors(path: Path) -> pd.DataFrame:
    """Fit a historical NCAA-to-NBA calibration and score unlabelled prospects.

    The CSV contains historical rookie rows with nba_pdk_per_min labels and
    current draft-class rows with that target left blank. At least four draft
    classes and forty historical players are required before college data is
    allowed to influence a forecast.
    """
    columns = [
        "player_name", "player_key", "college_projected_pdk_per_min",
        "nba_rookie_rate_baseline", "college_prior_base_weight",
        "college_cv_mae", "college_baseline_cv_mae",
        "college_projected_minutes_per_game", "college_minutes_prior_weight",
        "college_minutes_cv_mae", "college_minutes_baseline_cv_mae",
        "college_target_source",
    ]
    if not path.exists():
        warnings.warn(
            f"Prior rookie college non attivo: manca {path}. Aggiungi i dati NCAA e gli esiti NBA storici.",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path)
    required = {"player_name", "nba_pdk_per_min"}
    if not required.issubset(raw.columns):
        warnings.warn(
            f"Prior rookie college non attivo: {path} deve contenere player_name e nba_pdk_per_min.",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)
    if not {"games", "minutes_per_game", "points_per_game"}.issubset(raw.columns):
        warnings.warn(
            f"Prior rookie college non attivo: mancano statistiche college obbligatorie in {path}.",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)

    raw["player_key"] = raw["player_name"].map(player_key)
    draft_years = _number(raw, "draft_year")
    target = _number(raw, "nba_pdk_per_min")
    rookie_minutes = _number(raw, "nba_rookie_minutes")
    target_source = "nba_boxscore_proxy_pdk_per_min"

    # Prefer verified official Dunkest labels when a reproducible official
    # rookie-season dataset is available. Do not mix official labels with the
    # older box-score proxy in a single fit: use one target definition per model.
    official_path = path.with_name("rookie_official_pdk.csv")
    if official_path.exists():
        official = pd.read_csv(official_path)
        required_official = {
            "player_key", "draft_year", "official_dunkest_pdk_per_min",
            "official_dunkest_rookie_minutes",
        }
        if required_official.issubset(official.columns):
            official["player_key"] = official["player_key"].astype(str)
            official["draft_year"] = pd.to_numeric(official["draft_year"], errors="coerce")
            if official.duplicated(["player_key", "draft_year"]).any():
                raise ValueError(f"Duplicate player/draft-year labels in {official_path}.")
            raw = raw.merge(
                official[list(required_official)],
                on=["player_key", "draft_year"],
                how="left",
                validate="one_to_one",
            )
            official_target = _number(raw, "official_dunkest_pdk_per_min")
            official_eligible = official_target.notna() & draft_years.notna()
            if (
                int(official_eligible.sum()) >= MIN_HISTORY_ROWS
                and draft_years.loc[official_eligible].nunique() >= MIN_DRAFT_CLASSES
            ):
                target = official_target
                rookie_minutes = _number(raw, "official_dunkest_rookie_minutes")
                target_source = "official_dunkest_pdk_per_min"

    features = _college_features(raw)
    historical = target.notna() & features["college_pdk_per_min"].notna()
    eligible = historical & draft_years.notna()
    if int(eligible.sum()) < MIN_HISTORY_ROWS or draft_years.loc[eligible].nunique() < MIN_DRAFT_CLASSES:
        warnings.warn(
            "Prior rookie college non attivo: servono almeno "
            f"{MIN_HISTORY_ROWS} rookie con esito NBA e {MIN_DRAFT_CLASSES} classi draft "
            f"(trovati {int(eligible.sum())} giocatori, "
            f"{draft_years.loc[eligible].nunique()} classi).",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)

    # Evaluate the NCAA prior on later draft classes only. Feature selection,
    # imputation, scaling, and the baseline are refit inside every fold.
    ordered_years = sorted(draft_years.loc[eligible].dropna().unique())
    cv_actual: list[float] = []
    cv_prediction: list[float] = []
    cv_baseline: list[float] = []
    for split in range(2, len(ordered_years)):
        train_years = ordered_years[:split]
        validation_years = ordered_years[split:split + 1]
        train_mask = eligible & draft_years.isin(train_years)
        validation_mask = eligible & draft_years.isin(validation_years)
        if int(train_mask.sum()) < MIN_CV_TRAIN_ROWS or int(validation_mask.sum()) < MIN_CV_VALIDATION_ROWS:
            continue
        fold_x = features.loc[train_mask, _NUMERIC_FEATURES + ["position_G", "position_F", "position_C"]]
        fold_x = fold_x.loc[:, fold_x.notna().any(axis=0)]
        fold_medians = fold_x.median().fillna(0.0)
        fold_model = make_pipeline(StandardScaler(), Ridge(alpha=20.0))
        fold_model.fit(
            fold_x.fillna(fold_medians),
            target.loc[train_mask].clip(0.0, 1.5),
            ridge__sample_weight=_rookie_sample_weights(
                rookie_minutes.loc[train_mask]
            ).to_numpy(dtype=float),
        )
        validation_x = features.loc[validation_mask, fold_x.columns].fillna(fold_medians)
        cv_actual.extend(target.loc[validation_mask].clip(0.0, 1.5).tolist())
        cv_prediction.extend(np.clip(fold_model.predict(validation_x), 0.0, 1.5).tolist())
        cv_baseline.extend(
            np.repeat(
                float(target.loc[train_mask].clip(0.0, 1.5).median()),
                int(validation_mask.sum()),
            ).tolist()
        )

    if len(cv_actual) < MIN_CV_VALIDATION_ROWS * MIN_CV_FOLDS:
        warnings.warn(
            "Prior rookie college non attivo: i cohort storici non permettono una validazione temporale sufficiente.",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)
    cv_mae = float(np.mean(np.abs(np.asarray(cv_actual) - np.asarray(cv_prediction))))
    baseline_cv_mae = float(np.mean(np.abs(np.asarray(cv_actual) - np.asarray(cv_baseline))))
    relative_gain = (baseline_cv_mae - cv_mae) / max(baseline_cv_mae, 1e-9)
    calibrated_base_weight = COLLEGE_PRIOR_BASE_WEIGHT * float(
        np.clip(relative_gain / FULL_WEIGHT_RELATIVE_MAE_GAIN, 0.0, 1.0)
    )
    if calibrated_base_weight <= 0.0:
        warnings.warn(
            "Prior rookie college non attivo: la validazione temporale non batte il baseline NBA rookie; "
            "i rookie useranno la stima conservativa da listino e ruolo.",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)

    requested_columns = _NUMERIC_FEATURES + ["position_G", "position_F", "position_C"]
    x_train = features.loc[eligible, requested_columns]
    # Do not turn unavailable source fields into fabricated all-zero signals.
    x_train = x_train.loc[:, x_train.notna().any(axis=0)]
    medians = x_train.median().fillna(0.0)
    model = make_pipeline(StandardScaler(), Ridge(alpha=20.0))
    model.fit(
        x_train.fillna(medians),
        target.loc[eligible].clip(0.0, 1.5),
        ridge__sample_weight=_rookie_sample_weights(
            rookie_minutes.loc[eligible]
        ).to_numpy(dtype=float),
    )

    # Missing NBA labels in older cohorts usually mean no rookie-season NBA
    # minutes were found; they are not prospects. Only score the latest draft
    # cohort, which is the current incoming class.
    current_draft_year = draft_years.max()
    candidates = (
        target.isna()
        & draft_years.eq(current_draft_year)
        & features["college_pdk_per_min"].notna()
    )
    if not candidates.any():
        warnings.warn(
            "Prior rookie college calibrato ma senza rookie attuali da valutare: "
            "aggiungi righe della classe draft corrente lasciando vuoto nba_pdk_per_min.",
            RuntimeWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)
    x_current = features.loc[candidates, x_train.columns].fillna(medians)
    predictions = np.clip(model.predict(x_current), 0.0, 1.5)
    result = pd.DataFrame(
        {
            "player_name": raw.loc[candidates, "player_name"].astype(str).values,
            "college_projected_pdk_per_min": predictions,
            "nba_rookie_rate_baseline": float(target.loc[eligible].median()),
            "college_prior_base_weight": calibrated_base_weight,
            "college_cv_mae": cv_mae,
            "college_baseline_cv_mae": baseline_cv_mae,
            "college_target_source": target_source,
        }
    )
    result["player_key"] = result["player_name"].map(player_key)
    minutes_prior = _historical_rookie_minutes_prior(raw, features, draft_years)
    if not minutes_prior.empty:
        result = result.merge(
            minutes_prior.drop(columns="player_name"), on="player_key", how="left", validate="one_to_one"
        )
    else:
        for column in columns:
            if column not in result:
                result[column] = np.nan
    return result[columns].drop_duplicates("player_key", keep="last").reset_index(drop=True)
