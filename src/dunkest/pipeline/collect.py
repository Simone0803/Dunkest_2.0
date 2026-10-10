from __future__ import annotations

from dunkest.config import Settings
from dunkest.data.access import (
    get_coach_data,
    get_dunkest_data,
    get_injuries,
    get_player_data,
    get_schedule,
    get_team_data,
)


def run_collect(settings: Settings, force_refresh: bool = False) -> dict[str, int]:
    summary = {
        "players_dunkest": len(get_dunkest_data(settings, force_refresh=force_refresh)),
        "injuries": len(get_injuries(settings, force_refresh=force_refresh)),
        "player_logs": len(get_player_data(settings, force_refresh=force_refresh)),
        "team_logs": len(get_team_data(settings, force_refresh=force_refresh)),
        "schedule": len(get_schedule(settings, force_refresh=force_refresh)),
        "coaches": len(get_coach_data(settings, force_refresh=force_refresh)),
    }
    return summary
