from __future__ import annotations

import numpy as np
import pandas as pd
import hashlib

from dunkest.rules.pdk import pdk_from_boxscore_row


def synthetic_logs_from_dunkest(dunkest_df: pd.DataFrame, n_games: int = 12) -> pd.DataFrame:
    """Fallback player logs when nba_api collection is unavailable or slow."""
    rows: list[dict] = []
    for _, p in dunkest_df.iterrows():
        name = p["player_name"]
        base_pdk = float(p.get("pdk", 15))
        base_min = float(p.get("min", 20))
        team = p.get("team_code", "")
        seed = int.from_bytes(hashlib.sha256(str(name).encode("utf-8")).digest()[:4], "big")
        rng = np.random.default_rng(seed)
        for g in range(n_games):
            noise = rng.normal(0, 3)
            pdk = max(base_pdk + noise, 0)
            pts = pdk * 0.45
            row = {
                "PLAYER_NAME": name,
                "GAME_DATE": pd.Timestamp("2025-11-01") + pd.Timedelta(days=g * 3),
                "MIN": base_min,
                "PTS": pts,
                "REB": base_pdk * 0.15,
                "AST": base_pdk * 0.12,
                "STL": 1,
                "BLK": 0.5,
                "TOV": 2,
                "OREB": 1,
                "DREB": 3,
                "FGM": pts * 0.4,
                "FGA": pts * 0.8,
                "FTM": 2,
                "FTA": 3,
                "FG3M": 1,
                "TEAM_ABBREVIATION": team,
                "OPPONENT": "OPP",
                "MATCHUP": f"{team} vs. OPP",
            }
            row["PDK"] = pdk_from_boxscore_row(pd.Series(row))
            rows.append(row)
    return pd.DataFrame(rows)
