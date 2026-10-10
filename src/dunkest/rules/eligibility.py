from __future__ import annotations

import re

import pandas as pd

from dunkest.names import player_key, player_surname

HARD_OUT_STATUSES = {
    "OUT",
    "OUT FOR SEASON",
    "INACTIVE",
    "INDISPONIBILE",
    "FUORI",
    "IR",
    "INJURED RESERVE",
    "SUSPENDED",
    "INJURED",
    "UNAVAILABLE",
}

# Kept for callers that still import the old name; hard-outs only.
OUT_STATUSES = HARD_OUT_STATUSES

_UNCERTAIN_PLAY_PROB = {
    "DOUBTFUL": 0.25,
    "QUESTIONABLE": 0.50,
    "GAME TIME DECISION": 0.75,
    "GTD": 0.75,
}

_HARD_GROUPS = {"INDISPONIBILI", "UNAVAILABLE", "INJURED"}


def _clean_status(value: object) -> str:
    return (
        str(value or "")
        .upper()
        .strip()
        .replace("-", " ")
    )


def _status_letters(value: object) -> str:
    return re.sub(r"[^A-Z ]", "", _clean_status(value))


def play_probability(status: object = "", lineup_group: object = "") -> float:
    group = str(lineup_group or "").upper().strip()
    if group in _HARD_GROUPS:
        return 0.0
    letters = _status_letters(status)
    if letters in HARD_OUT_STATUSES or letters.startswith(("OUT ", "INACTIVE ")):
        return 0.0
    for token, prob in _UNCERTAIN_PLAY_PROB.items():
        if token in letters:
            return prob
    return 1.0


def unavailable_mask(df: pd.DataFrame) -> pd.Series:
    """True only for players who should not be bought (confirmed out)."""
    unavailable = pd.Series(False, index=df.index)
    if "lineup_group" in df.columns:
        group = df["lineup_group"].astype(str).str.upper().str.strip()
        unavailable |= group.isin(_HARD_GROUPS)
    if "status" in df.columns:
        status = (
            df["status"].astype(str).str.upper().str.strip().str.replace(r"[^A-Z ]", "", regex=True)
        )
        unavailable |= (
            status.isin(HARD_OUT_STATUSES)
            | status.str.startswith(("OUT ", "INACTIVE "))
        )
    return unavailable


def _initial_token(name: object) -> str:
    tokens = player_key(name).split()
    return tokens[0][0] if tokens else ""


def filter_injured(df: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    if injuries.empty or "player_name" not in injuries.columns:
        return df
    inj = injuries.copy()
    inj["key"] = inj["player_name"].map(player_key)
    unavailable = unavailable_mask(inj)
    out_rows = inj.loc[unavailable]
    out_keys = set(out_rows["key"].tolist())
    df = df.copy()
    keys = df["player_name"].map(player_key)
    remove = keys.isin(out_keys)

    out_surnames = {player_surname(name) for name in out_rows["player_name"].astype(str)}
    out_surnames.discard("")
    surnames = df["player_name"].map(player_surname)
    counts = surnames.value_counts()
    unique_surnames = {name for name in out_surnames if counts.get(name, 0) == 1}
    remove |= surnames.isin(unique_surnames)

    if "team" in df.columns and "team" in inj.columns:
        team_series = df["team"].astype(str).str.casefold()
        for _, injury in out_rows.iterrows():
            surname = player_surname(injury.get("player_name", ""))
            team = str(injury.get("team", "")).strip().casefold()
            if surname and team:
                remove |= surnames.eq(surname) & team_series.eq(team)

    # Abbreviated injury names ("D. Barlow", "S. Curry") must still hit full
    # market names when the initial + surname pair is unique on that team or
    # across the pool.
    for _, injury in out_rows.iterrows():
        injury_key = player_key(injury.get("player_name", ""))
        tokens = injury_key.split()
        if len(tokens) < 2 or len(tokens[0]) > 1:
            continue
        initial, surname = tokens[0], tokens[-1]
        team = str(injury.get("team", "")).strip().casefold()
        candidates = df.loc[surnames.eq(surname)]
        if team and "team" in df.columns:
            team_hits = candidates.loc[
                candidates["team"].astype(str).str.casefold().eq(team)
            ]
            if not team_hits.empty:
                candidates = team_hits
        initial_hits = candidates.loc[
            candidates["player_name"].map(_initial_token).eq(initial)
        ]
        if len(initial_hits) == 1:
            remove |= df.index.isin(initial_hits.index)
        elif len(initial_hits) == 0 and len(candidates) == 1:
            remove |= df.index.isin(candidates.index)
    return df.loc[~remove].copy()
