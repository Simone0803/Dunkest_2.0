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
    # pandas.NA cannot be used in a boolean expression (value or "").
    # Scraped/merged injury feeds routinely contain nullable status cells.
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).upper().strip().replace("-", " ")


def _status_letters(value: object) -> str:
    return re.sub(r"[^A-Z ]", "", _clean_status(value))


def play_probability(status: object = "", lineup_group: object = "") -> float:
    group = _clean_status(lineup_group)
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

    surnames = df["player_name"].map(player_surname)
    team_series = df["team"].astype(str).str.strip().str.casefold() if "team" in df.columns else None

    # Resolve each hard-out identity conservatively. Never remove every player
    # sharing a surname on the same team before considering the initial: an
    # injury row such as "J. Miller, LAC" must exclude Jordan Miller, not Baba
    # Miller as well. If a team-specific match is unavailable, only fall back to
    # a unique surname across the full candidate pool.
    for _, injury in out_rows.iterrows():
        injury_name = str(injury.get("player_name", "")).strip()
        injury_key = player_key(injury_name)
        tokens = injury_key.split()
        surname = player_surname(injury_name)
        if not surname:
            continue
        candidates = df.loc[surnames.eq(surname)]
        team = str(injury.get("team", "")).strip().casefold()
        if team and team_series is not None:
            team_hits = candidates.loc[team_series.loc[candidates.index].eq(team)]
            # A source-provided team is a hard identity constraint. If that
            # team has no candidate, never fall back to another team's player.
            if team_hits.empty:
                continue
            candidates = team_hits
        elif len(candidates) != 1:
            continue

        if len(tokens) >= 2 and len(tokens[0]) == 1:
            initial = tokens[0]
            initial_hits = candidates.loc[
                candidates["player_name"].map(_initial_token).eq(initial)
            ]
            if len(initial_hits) == 1:
                remove |= df.index.isin(initial_hits.index)
            elif len(initial_hits) == 0 and len(candidates) == 1:
                # OCR may lose or corrupt an initial; allow only a unique
                # surname candidate, never a multi-player surname collision.
                remove |= df.index.isin(candidates.index)
        elif len(tokens) == 1 and len(candidates) == 1:
            # Surname-only UI labels may be resolved only when unique. A full
            # official name with a different first name must never be reduced
            # to a surname-only match, even if it is the sole same-team candidate.
            remove |= df.index.isin(candidates.index)
    return df.loc[~remove].copy()
