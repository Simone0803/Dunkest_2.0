from __future__ import annotations

import pandas as pd


def _fga_missed(row: pd.Series) -> float:
    return max(float(row.get("FGA", 0)) - float(row.get("FGM", 0)), 0)


def _fta_missed(row: pd.Series) -> float:
    return max(float(row.get("FTA", 0)) - float(row.get("FTM", 0)), 0)


def pdk_from_boxscore_row(row: pd.Series, team_won: bool | None = None) -> float:
    """Reconstruct Dunkest PDK from an NBA box score (official-rule approximation).

    Dunkest's official scoring feed remains authoritative; the NBA box score does
    not expose every fantasy-specific event, so this is a historical proxy.
    """
    pts = float(row.get("PTS", 0))
    oreb = float(row.get("OREB", 0))
    dreb = float(row.get("DREB", 0))
    ast = float(row.get("AST", 0))
    stl = float(row.get("STL", 0))
    blk = float(row.get("BLK", 0))
    blka = float(row.get("BLKA", 0))
    tov = float(row.get("TOV", 0))
    fg3m = float(row.get("FG3M", row.get("TPM", 0)))

    score = (
        pts * 1.0
        + dreb * 1.0
        + oreb * 1.25
        + ast * 1.5
        + stl * 1.5
        - tov * 1.5
        + blk * 1.5
        - blka * 0.5
        - _fga_missed(row) * 1.0
        - _fta_missed(row) * 1.0
    )
    if fg3m >= 5:
        score += 5
    elif fg3m >= 4:
        score += 4
    elif fg3m >= 3:
        score += 3

    reb = oreb + dreb
    categories = sum(value >= 10 for value in (pts, reb, ast, stl, blk))
    if categories >= 4:
        score += 50
    elif categories == 3:
        score += 10
    elif categories == 2:
        score += 5

    starter = str(row.get("START_POSITION", "")).strip()
    if starter and starter.lower() not in {"nan", "none", "0", "false"}:
        score += 1

    if team_won is not None and pd.notna(team_won) and bool(team_won):
        score *= 1.05
    return float(score)


def normalize_position(pos_str: str) -> str:
    s = str(pos_str).upper()
    if s in {"P", "PG", "PLAYMAKER", "PLAY MAKER"}:
        return "G"
    if s in {"A", "ALA", "WING"}:
        return "F"
    if "C" in s and "G" not in s and "F" not in s:
        return "C"
    if any(k in s for k in ("PG", "SG", "G", "GUARD")):
        return "G"
    if any(k in s for k in ("SF", "PF", "F", "FORWARD")):
        return "F"
    if s and s[0] in ("G", "F", "C"):
        return s[0]
    raise ValueError(f"Unsupported player position: {pos_str!r}")
