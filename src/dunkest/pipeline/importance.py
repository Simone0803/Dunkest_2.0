from __future__ import annotations

import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance

from dunkest.config import Settings
from dunkest.models.predictor import FEATURE_COLS, train_models


CATEGORY_MAP = {
    "pdk_": "player_form",
    "min_": "minutes",
    "opp_": "matchup",
    "team_": "team",
    "injury": "injury",
    "rest_": "schedule",
    "is_b2b": "schedule",
    "cr": "market_value",
}


def feature_importance_summary(settings: Settings, features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame(columns=["feature", "importance", "category"])
    models, _ = train_models(settings, features)
    cols = models.get("_feature_cols", [])
    df = features.dropna(subset=["target_pdk"]).copy()
    if "GAME_DATE" not in df or len(df) < 120:
        return pd.DataFrame(columns=["feature", "importance", "category"])
    dates = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    unique_dates = dates.dropna().sort_values().unique()
    if len(unique_dates) < 5:
        return pd.DataFrame(columns=["feature", "importance", "category"])
    split = max(1, min(len(unique_dates) - 1, int(len(unique_dates) * 0.8)))
    cutoff = unique_dates[split]
    train_mask = dates.lt(cutoff)
    valid_mask = dates.ge(cutoff)
    if int(train_mask.sum()) < 80 or int(valid_mask.sum()) < 40:
        return pd.DataFrame(columns=["feature", "importance", "category"])
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    medians = df.loc[train_mask, cols].median()
    X_train = df.loc[train_mask, cols].fillna(medians).fillna(0.0)
    X_valid = df.loc[valid_mask, cols].fillna(medians).fillna(0.0)
    baseline = pd.to_numeric(
        df.get("expected_pdk_minutes_model", pd.Series(0.0, index=df.index)),
        errors="coerce",
    ).fillna(0.0)
    y = pd.to_numeric(df["target_pdk"], errors="coerce") - baseline
    base_model = models.get("rf") or models.get("ridge")
    if base_model is None:
        return pd.DataFrame()
    validation_model = clone(base_model)
    validation_model.fit(X_train, y.loc[train_mask])
    result = permutation_importance(
        validation_model,
        X_valid,
        y.loc[valid_mask],
        n_repeats=5,
        random_state=settings.random_state,
        n_jobs=1,
    )
    rows = []
    for feat, imp in zip(cols, result.importances_mean):
        cat = "other"
        for prefix, name in CATEGORY_MAP.items():
            if feat.startswith(prefix) or feat == prefix.rstrip("_"):
                cat = name
                break
        rows.append({"feature": feat, "importance": float(imp), "category": cat})
    out = pd.DataFrame(rows).sort_values("importance", ascending=False)
    agg = out.groupby("category", as_index=False)["importance"].sum()
    agg["feature"] = "AGG"
    return pd.concat([out, agg], ignore_index=True)
