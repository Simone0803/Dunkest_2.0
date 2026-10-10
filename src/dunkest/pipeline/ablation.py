from __future__ import annotations

import pandas as pd

from dunkest.config import Settings
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models
from copy import copy


def run_ablation_summary(
    settings: Settings,
    player_logs: pd.DataFrame,
    team_logs: pd.DataFrame,
    injuries: pd.DataFrame,
    schedule: pd.DataFrame | None = None,
    target_gameweek: int | None = None,
) -> pd.DataFrame:
    configs = [
        ("baseline", {"use_matchup": False, "use_injuries": False, "use_schedule": False}),
        ("plus_schedule", {"use_matchup": False, "use_injuries": False, "use_schedule": True}),
        ("plus_matchup", {"use_matchup": True, "use_injuries": False, "use_schedule": False}),
        # Availability is an optimizer filter, not a PDK-rate feature, so it
        # cannot be measured honestly with this player-level MAE table.
        ("full", {"use_matchup": True, "use_injuries": False, "use_schedule": True}),
    ]
    rows: list[dict] = []
    for name, flags in configs:
        s = copy(settings)
        s.use_matchup = flags["use_matchup"]
        s.use_injuries = flags["use_injuries"]
        s.use_schedule = flags["use_schedule"]
        if target_gameweek is not None:
            s.target_gameweek = int(target_gameweek)
        feats = build_feature_matrix(
            s,
            player_logs,
            team_logs,
            injuries,
            schedule=schedule,
            team_overrides=None,
            target_gameweek=target_gameweek,
            include_completed_schedule=target_gameweek is not None,
        )
        if feats.empty:
            mae = float("nan")
        else:
            models, pred = train_models(s, feats)
            y = feats.dropna(subset=["target_pdk"])["target_pdk"]
            valid_idx = y.index.intersection(pred.index[pred.notna()])
            mae = float((y.loc[valid_idx] - pred.loc[valid_idx]).abs().mean()) if len(valid_idx) else float("nan")
        rows.append({"variant": name, "player_pdk_mae": mae})
    return pd.DataFrame(rows)
