"""Safely attach verified official Dunkest PDK labels to NBA game logs."""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

KEYS = ["PLAYER_ID", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION"]
OFFICIAL_LABEL = "PDK_OFFICIAL_VALID"


def _normalize_identifier(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _canonical_keys(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    out = frame.copy()
    if "GAME_ID" not in out and "Game_ID" in out:
        out = out.rename(columns={"Game_ID": "GAME_ID"})
    missing = sorted(set(KEYS) - set(out.columns))
    if missing:
        raise ValueError(f"{source} lacks official PDK join keys: {missing}")
    out["PLAYER_ID"] = out["PLAYER_ID"].map(_normalize_identifier)
    out["GAME_ID"] = out["GAME_ID"].map(_normalize_identifier)
    out["GAME_DATE"] = (
        pd.to_datetime(out["GAME_DATE"], errors="coerce", utc=True)
        .dt.tz_convert(None)
        .dt.normalize()
    )
    out["TEAM_ABBREVIATION"] = (
        out["TEAM_ABBREVIATION"].astype("string").str.strip().str.upper()
    )
    if out[KEYS].isna().any().any():
        raise ValueError(f"{source} contains missing official PDK join keys.")
    if out.duplicated(KEYS).any():
        raise ValueError(f"{source} has duplicate official PDK join keys.")
    return out[KEYS].reset_index(drop=True)


def attach_official_pdk_labels(
    player_logs: pd.DataFrame,
    data_path: str | Path,
    season: str,
) -> pd.DataFrame:
    """Attach labels from a versioned local overlay, retaining proxy PDK.

    The join is one-to-one on NBA player/game/date/team identity. Missing labels
    remain null, so target selection can safely fall back to the proxy target.
    """
    if player_logs.empty:
        return player_logs.copy()

    processed = Path(data_path) / "processed"
    candidates = [
        processed / f"player_game_logs_{season}_official_pdk_overlay_v4.parquet",
        processed / f"player_game_logs_{season}_official_pdk_overlay.parquet",
    ]
    overlay_path = next((path for path in candidates if path.exists()), None)
    if overlay_path is None:
        out = player_logs.copy()
        if OFFICIAL_LABEL in out:
            out[OFFICIAL_LABEL] = pd.to_numeric(out[OFFICIAL_LABEL], errors="coerce")
        return out

    if OFFICIAL_LABEL not in player_logs.columns and not set(KEYS).issubset(
        player_logs.columns
    ) and not ({"PLAYER_ID", "Game_ID", "GAME_DATE", "TEAM_ABBREVIATION"} <= set(player_logs.columns)):
        warnings.warn(
            f"Cannot attach official PDK labels from {overlay_path}: player log identity keys are missing; using proxy labels.",
            RuntimeWarning,
            stacklevel=2,
        )
        return player_logs.copy()

    overlay = pd.read_parquet(overlay_path)
    required_overlay = set(KEYS + [OFFICIAL_LABEL])
    if not required_overlay.issubset(overlay.columns):
        raise ValueError(
            f"Official PDK overlay {overlay_path} lacks columns: "
            f"{sorted(required_overlay - set(overlay.columns))}"
        )

    try:
        base_keys = _canonical_keys(player_logs, source="Player logs")
        overlay_keys = _canonical_keys(overlay, source=f"Official overlay {overlay_path}")
    except ValueError as exc:
        warnings.warn(
            f"Cannot safely attach official PDK labels from {overlay_path}: {exc}; using existing targets.",
            RuntimeWarning,
            stacklevel=2,
        )
        return player_logs.copy()

    labels = overlay_keys.copy()
    labels[OFFICIAL_LABEL] = pd.to_numeric(overlay[OFFICIAL_LABEL], errors="coerce").reset_index(drop=True)
    joined = base_keys.merge(
        labels, on=KEYS, how="left", validate="one_to_one", indicator=True, sort=False
    )
    matched = int(joined["_merge"].eq("both").sum())
    if matched == 0:
        warnings.warn(
            f"Official PDK overlay {overlay_path} matched no player-game rows; using existing targets.",
            RuntimeWarning,
            stacklevel=2,
        )
        return player_logs.copy()
    if matched < len(player_logs):
        warnings.warn(
            f"Official PDK overlay matched {matched}/{len(player_logs)} player-game rows for {season}; unmatched rows will retain null official labels.",
            RuntimeWarning,
            stacklevel=2,
        )

    out = player_logs.copy().reset_index(drop=True)
    out[OFFICIAL_LABEL] = joined[OFFICIAL_LABEL].to_numpy()
    return out
