from pathlib import Path

import pandas as pd

from dunkest.config import Settings
from dunkest.data.dunkest import client


def _official_injury_payload() -> dict:
    return {
        "data": {
            "players": [
                {
                    "id": 1,
                    "first_name": "Jimmy",
                    "last_name": "Butler",
                    "team": {"abbreviation": "GSW", "name": "Golden State Warriors"},
                    "injury": {
                        "date": "2026-10-14",
                        "reason": "Ginocchio",
                        "description": "Indisponibile fino al 2 Gen",
                    },
                },
                {
                    "id": 2,
                    "first_name": "Kristaps",
                    "last_name": "Porzingis",
                    "team": {"abbreviation": "GSW", "name": "Golden State Warriors"},
                    "injury": {
                        "date": "2026-10-14",
                        "reason": "Polpaccio",
                        "description": "GTD: da valutare prima della partita",
                    },
                },
                {
                    "id": 3,
                    "first_name": "Stephen",
                    "last_name": "Curry",
                    "team": {"abbreviation": "GSW", "name": "Golden State Warriors"},
                    "injury": None,
                },
            ]
        }
    }


def test_official_fantasy_injury_payload_distinguishes_out_from_gtd():
    result = client._parse_fantasy_injuries_payload(_official_injury_payload())

    assert result[["player_name", "status", "team"]].to_dict("records") == [
        {"player_name": "Jimmy Butler", "status": "OUT", "team": "GSW"},
        {"player_name": "Kristaps Porzingis", "status": "GAME TIME DECISION", "team": "GSW"},
    ]
    assert result.loc[0, "injury_reason"] == "Ginocchio"
    assert result.loc[0, "source_url"] == "https://fantasy.dunkest.com/1/injuries"


def test_scrape_injuries_uses_official_fantasy_browser_payload_not_legacy_site(monkeypatch):
    monkeypatch.setattr(client, "_fetch_fantasy_injuries_payload", lambda settings: _official_injury_payload())
    monkeypatch.setattr(
        client,
        "get_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy site must not be queried")),
    )

    result = client.scrape_injuries(Settings())

    assert len(result) == 2
    assert set(result["team"]) == {"GSW"}


def test_official_injury_parser_fails_closed_on_incomplete_api_payload():
    import pytest

    with pytest.raises(RuntimeError, match="data.players"):
        client._parse_fantasy_injuries_payload({"data": {}})


def test_unknown_injury_description_is_not_assumed_out():
    assert client._injury_status_from_description("") == "UNKNOWN"
    assert client._injury_status_from_description("dolore al ginocchio") == "UNKNOWN"


def test_abbreviated_injury_name_matches_full_player_with_team_and_initial():
    from dunkest.models.predictor import _match_injury_record
    from dunkest.rules.eligibility import play_probability
    from dunkest.names import player_key, player_surname

    records = [{
        "key": player_key("C. White"),
        "surname": player_surname("C. White"),
        "team": "CHA",
        "p_play": play_probability("GAME TIME DECISION"),
        "status": "GAME TIME DECISION",
    }]

    matched = _match_injury_record("Coby White", "CHA", records)
    assert matched is not None
    assert matched["p_play"] == 0.75
    assert _match_injury_record("Coby White", "CHI", records) is None


def test_abbreviated_injury_match_refuses_ambiguous_same_initial_surname():
    from dunkest.models.predictor import _match_injury_record
    from dunkest.rules.eligibility import play_probability
    from dunkest.names import player_key, player_surname

    records = [{
        "key": player_key(name),
        "surname": player_surname(name),
        "team": "OKC",
        "p_play": play_probability("GAME TIME DECISION"),
        "status": "GAME TIME DECISION",
    } for name in ("J. Williams", "Jalen Williams", "Jaylin Williams")]

    assert _match_injury_record("Jalen Williams", "OKC", records)["key"] == player_key("Jalen Williams")


def test_official_full_name_does_not_match_another_player_by_surname_alone():
    from dunkest.models.predictor import _match_injury_record
    from dunkest.rules.eligibility import play_probability
    from dunkest.names import player_key, player_surname

    records = [{
        "key": player_key("Baba Miller"),
        "surname": player_surname("Baba Miller"),
        "team": "LAC",
        "p_play": play_probability("OUT"),
        "status": "OUT",
    }]

    assert _match_injury_record("Jordan Miller", "LAC", records) is None
    assert _match_injury_record("Baba Miller", "LAC", records)["key"] == player_key("Baba Miller")


def test_play_probability_handles_nullable_status_and_lineup_group():
    import numpy as np
    from dunkest.rules.eligibility import play_probability

    for missing in (None, np.nan, pd.NA):
        assert play_probability(missing, missing) == 1.0
    assert play_probability("OUT", pd.NA) == 0.0
    assert play_probability(pd.NA, "UNAVAILABLE") == 0.0


def test_injury_matching_handles_nullable_identity_fields():
    from dunkest.models.predictor import _match_injury_record

    assert _match_injury_record(pd.NA, pd.NA, []) is None



def test_injury_classification_separates_season_ending_temporary_and_rest():
    classify = client._injury_classification
    assert classify("Indisponibile per tutta la stagione", "Ginocchio", "2026-10-14", "OUT") == (
        "SEASON_ENDING", "SEASON_ENDING", None
    )
    assert classify("Indisponibile fino al 2 Nov", "Piede", "2026-10-14", "OUT") == (
        "TEMPORARY_OUT", "MEDIUM_TERM", 19
    )
    assert classify("GTD: da valutare prima della partita", "Riposo", "2026-10-14", "GAME TIME DECISION") == (
        "REST", "REST", None
    )
    assert classify("GTD: da valutare prima della partita", "Ginocchio", "2026-10-14", "GAME TIME DECISION") == (
        "DAY_TO_DAY", "UNCERTAIN", None
    )


def test_official_parser_adds_explicit_severity_fields():
    payload = _official_injury_payload()
    result = client._parse_fantasy_injuries_payload(payload)
    butler = result.loc[result["player_name"].eq("Jimmy Butler")].iloc[0]
    porzingis = result.loc[result["player_name"].eq("Kristaps Porzingis")].iloc[0]
    assert butler["injury_type"] == "TEMPORARY_OUT"
    assert butler["injury_severity"] == "LONG_TERM"
    assert not bool(butler["season_ending"])
    assert porzingis["injury_type"] == "DAY_TO_DAY"
    assert porzingis["injury_severity"] == "UNCERTAIN"
