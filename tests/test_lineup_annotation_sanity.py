import pandas as pd
import pytest

from dunkest.models.predictor import _sanitize_lineup_annotations


def test_team_wide_starter_count_is_preserved_without_fixture_scope():
    # One team can have multiple NBA fixtures in a Dunkest gameweek. A count
    # above five across the merged gameweek is not enough to invalidate labels.
    market = pd.DataFrame([
        {"player_name": f"CLE Starter {i}", "team_code": "CLE", "lineup_group": "QUINTETTO", "starter": True, "status": "AVAILABLE"}
        for i in range(6)
    ] + [
        {"player_name": f"DEN Starter {i}", "team_code": "DEN", "lineup_group": "QUINTETTO", "starter": True, "status": "AVAILABLE"}
        for i in range(5)
    ])

    result = _sanitize_lineup_annotations(market)

    cle = result.team_code.eq("CLE")
    den = result.team_code.eq("DEN")
    assert result.loc[cle, "lineup_group"].eq("QUINTETTO").all()
    assert result.loc[cle, "starter"].all()
    assert result.loc[cle, "status"].eq("AVAILABLE").all()
    assert result.loc[den, "lineup_group"].eq("QUINTETTO").all()
    assert result.loc[den, "starter"].all()


def test_valid_starting_five_is_preserved():
    market = pd.DataFrame([
        {"player_name": f"Starter {i}", "team_code": "BOS", "lineup_group": "QUINTETTO", "starter": True}
        for i in range(5)
    ])

    result = _sanitize_lineup_annotations(market)

    assert result.lineup_group.eq("QUINTETTO").all()
    assert result.starter.all()
