from __future__ import annotations

import pandas as pd


def safe_postgame_retrieval_cutoff(values) -> tuple[pd.Timestamp, str]:
    """Return a conservative UTC cutoff for post-game result collection.

    NBA schedule feeds sometimes expose only a calendar date encoded as
    00:00 UTC, not the actual tipoff. In that case, requiring just four hours
    after midnight can allow collection while West Coast games are still live.
    Treat any midnight timestamp as date-only schedule precision and wait 36
    hours after the latest mapped date. When every timestamp has a real clock
    time, wait four hours after the latest kickoff.
    """
    times = pd.to_datetime(pd.Series(values), utc=True, errors="coerce")
    if times.empty or times.isna().any():
        raise ValueError("Fixture schedule contains missing or invalid UTC datetimes.")
    has_date_only = (
        times.dt.hour.eq(0)
        & times.dt.minute.eq(0)
        & times.dt.second.eq(0)
        & times.dt.microsecond.eq(0)
    ).any()
    if has_date_only:
        return times.dt.normalize().max() + pd.Timedelta(hours=36), "date_only_schedule_plus_36h"
    return times.max() + pd.Timedelta(hours=4), "exact_kickoff_plus_4h"
