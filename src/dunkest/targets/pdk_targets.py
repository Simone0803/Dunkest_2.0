from __future__ import annotations

import pandas as pd

from dunkest.rules.pdk import pdk_from_boxscore_row


def build_direct_pdk_target(features: pd.DataFrame) -> pd.Series:
    return features["target_pdk"]


def build_stat_targets(player_logs: pd.DataFrame) -> pd.DataFrame:
    cols = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "MIN"]
    out = player_logs[["PLAYER_NAME", "GAME_DATE"] + [c for c in cols if c in player_logs.columns]].copy()
    return out


def reconstruct_pdk_from_stats(row: pd.Series) -> float:
    return pdk_from_boxscore_row(row)
