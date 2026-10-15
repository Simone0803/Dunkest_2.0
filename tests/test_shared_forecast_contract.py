import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.pipeline.forecast import build_player_forecast


def test_shared_forecast_uses_same_predictor_and_eligibility_contract(monkeypatch):
    import dunkest.pipeline.forecast as module

    def fake_predict(settings, models, features, market, injuries, **kwargs):
        return pd.DataFrame({
            "player_name": ["Available Player", "Out Player"],
            "team": ["BOS", "NYK"],
            "expected_pdk": [12.0, 0.0],
        })

    def fake_filter(frame, injuries):
        return frame.loc[frame["player_name"].eq("Available Player")].copy()

    monkeypatch.setattr(module, "predict_players", fake_predict)
    monkeypatch.setattr(module, "filter_injured", fake_filter)
    result = build_player_forecast(
        Settings(use_injuries=True), {}, pd.DataFrame(), pd.DataFrame(),
        pd.DataFrame({"player_name": ["Out Player"], "status": ["OUT"]}),
        market_value_history=pd.DataFrame({"player_name": ["Available Player"]}),
        plusvalenza_history=pd.DataFrame({"player_name": ["Available Player"]}),
        college_rookie_priors=pd.DataFrame({"player_name": ["Rookie"]}),
        require_injury_snapshot=True,
    )

    assert result.raw["player_name"].tolist() == ["Available Player", "Out Player"]
    assert result.eligible["player_name"].tolist() == ["Available Player"]
    assert result.degradations == ()


def test_shared_forecast_fails_closed_when_required_historical_injuries_missing():
    with pytest.raises(RuntimeError, match="point-in-time injury snapshot"):
        build_player_forecast(
            Settings(use_injuries=True), {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            require_injury_snapshot=True,
        )
