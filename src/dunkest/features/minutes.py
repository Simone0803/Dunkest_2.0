from __future__ import annotations

import numpy as np
import pandas as pd


def expected_minutes_from_history(player_logs: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    """E[MIN] from rolling windows (time-safe per game row) plus a next-game row."""
    rows: list[dict] = []
    for name, g in player_logs.groupby("PLAYER_NAME"):
        g = g.sort_values("GAME_DATE").reset_index(drop=True)
        minutes = pd.to_numeric(g["MIN"], errors="coerce")
        item = pd.DataFrame(
            {
                "PLAYER_NAME": g["PLAYER_NAME"],
                "GAME_DATE": g["GAME_DATE"],
                "is_inference": False,
            }
        )
        for w in windows:
            item[f"e_min_{w}"] = (
                minutes.shift(1).rolling(window=w, min_periods=1).mean()
                if w > 0 else np.nan
            )
        item["e_min_season"] = minutes.expanding(min_periods=1).mean().shift(1)
        rows.extend(item.to_dict(orient="records"))

        inference = {
            "PLAYER_NAME": name,
            "GAME_DATE": pd.Timestamp(g.iloc[-1]["GAME_DATE"]) + pd.Timedelta(days=1),
            "is_inference": True,
        }
        for w in windows:
            inference[f"e_min_{w}"] = minutes.tail(w).mean() if w > 0 else np.nan
        inference["e_min_season"] = minutes.mean()
        rows.append(inference)
    return pd.DataFrame(rows)


def combine_minutes_and_pdk_per_min(
    features: pd.DataFrame, minute_feats: pd.DataFrame
) -> pd.DataFrame:
    minute_cols = [c for c in minute_feats.columns if c not in {"is_inference"}]
    merged = features.merge(minute_feats[minute_cols], on=["PLAYER_NAME", "GAME_DATE"], how="left")
    pdk_pm = merged["pdk_per_min_season"]
    minute_candidates = [c for c in ("e_min_5", "e_min_3", "e_min_10", "e_min_15") if c in merged]
    if not minute_candidates:
        minute_candidates = [c for c in merged if c.startswith("e_min_")]
    e_min = merged[minute_candidates[0]] if minute_candidates else pd.Series(np.nan, index=merged.index)
    merged["expected_pdk_minutes_model"] = e_min * pdk_pm
    return merged
