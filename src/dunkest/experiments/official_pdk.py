"""Utilities for experiments using official Dunkest PDK targets."""

from pathlib import Path

import pandas as pd


KEYS = [
    "PLAYER_ID",
    "GAME_ID",
    "GAME_DATE",
    "TEAM_ABBREVIATION",
]


def load_player_logs_with_official_pdk(
    base_path: str | Path,
    overlay_path: str | Path,
) -> pd.DataFrame:
    """Attach official PDK labels without changing the proxy PDK column."""
    base = pd.read_parquet(base_path)
    overlay = pd.read_parquet(overlay_path)

    required_base = set(KEYS + ["PDK"])
    required_overlay = set(KEYS + ["PDK_OFFICIAL_VALID"])

    if not required_base.issubset(base.columns):
        raise ValueError(f"Colonne mancanti nel dataset base: {required_base - set(base.columns)}")
    if not required_overlay.issubset(overlay.columns):
        raise ValueError(f"Colonne mancanti nell'overlay: {required_overlay - set(overlay.columns)}")

    for frame in (base, overlay):
        frame["GAME_DATE"] = pd.to_datetime(
            frame["GAME_DATE"], errors="coerce"
        ).dt.normalize()

    if base.duplicated(KEYS).any() or overlay.duplicated(KEYS).any():
        raise ValueError("Chiave non univoca: merge interrotto.")

    labels = overlay[KEYS + ["PDK_OFFICIAL_VALID"]].copy()

    merged = base.merge(
        labels,
        on=KEYS,
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    if not merged["_merge"].eq("both").all():
        missing = int(merged["_merge"].eq("left_only").sum())
        raise ValueError(f"{missing} righe base senza corrispondenza nell'overlay.")

    merged = merged.drop(columns="_merge")
    merged["PDK_OFFICIAL_VALID"] = pd.to_numeric(
        merged["PDK_OFFICIAL_VALID"], errors="coerce"
    )

    return merged
