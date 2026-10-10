import pandas as pd

from dunkest.config import Settings
from dunkest.data.dunkest import client


def test_historical_gameweek_without_official_rounds_returns_no_sample(monkeypatch):
    monkeypatch.setattr(client, "fetch_week_rounds", lambda _settings, _week: [])

    def unexpected_stats_call(*_args, **_kwargs):
        raise AssertionError("must not query invented round IDs")

    monkeypatch.setattr(client, "fetch_stats_table", unexpected_stats_call)

    result = client.fetch_dunkest_gameweek_players(Settings(), 17)

    assert result.empty


def test_historical_gameweek_uses_and_records_only_official_rounds(monkeypatch):
    seen = {}
    monkeypatch.setattr(client, "fetch_week_rounds", lambda _settings, _week: ["2", "4"])

    def fake_stats(_settings, **params):
        seen.update(params)
        return pd.DataFrame([{"player_name": "Player A", "pdk": 21.5}])

    monkeypatch.setattr(client, "fetch_stats_table", fake_stats)

    result = client.fetch_dunkest_gameweek_players(Settings(), 17)

    assert seen["rounds"] == ["2", "4"]
    assert result.loc[0, "gameweek"] == 17
    assert result.loc[0, "dunkest_rounds"] == "2,4"
