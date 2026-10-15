import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.pipeline import optimize as pipeline_optimize


def test_run_optimize_rejects_verified_neutral_baseline_without_team_score_evidence(monkeypatch):
    captured = {}

    def fake_optimizer(players, coaches, settings, **kwargs):
        captured["coaches"] = coaches.copy()
        return [object(), object(), object()]

    monkeypatch.setattr(pipeline_optimize, "optimize_top_k_lineups", fake_optimizer)
    coaches = pd.DataFrame([{
        "coach": "Coach A", "team": "BOS", "coach_cr": 8.0,
        "expected_coach_pdk": 4.5,
        "matchup_projection_available": True,
        "coach_projection_source": "verified_matchup_neutral_baseline",
    }])

    with pytest.raises(RuntimeError, match="proiezione basata su un matchup Dunkest verificato"):
        pipeline_optimize.run_optimize(Settings.from_yaml(), pd.DataFrame(), coaches)
    assert captured == {}


def test_run_optimize_requires_exactly_three_valid_lineups(monkeypatch):
    captured = {}

    def fake_optimizer(players, coaches, settings, **kwargs):
        captured["k"] = kwargs["k"]
        return [object(), object()]

    monkeypatch.setattr(pipeline_optimize, "optimize_top_k_lineups", fake_optimizer)
    coaches = pd.DataFrame([{
        "coach": "Coach A", "team": "BOS", "coach_cr": 8.0,
        "expected_coach_pdk": 4.5,
        "matchup_projection_available": True,
        "coach_projection_source": "verified_matchup",
    }])

    with pytest.raises(RuntimeError, match="ha prodotto 2 di 3 rose distinte valide"):
        pipeline_optimize.run_optimize(Settings.from_yaml(), pd.DataFrame(), coaches)

    assert captured["k"] == 3


def test_run_optimize_rejects_configuration_that_cannot_request_three_lineups(monkeypatch):
    def unexpected_optimizer(*args, **kwargs):
        pytest.fail("invalid lineup count must fail before invoking the solver")

    monkeypatch.setattr(pipeline_optimize, "optimize_top_k_lineups", unexpected_optimizer)
    settings = Settings.from_yaml()
    settings.optimizer_top_k = 2

    with pytest.raises(RuntimeError, match="richiede esattamente 3 rose"):
        pipeline_optimize.run_optimize(settings, pd.DataFrame(), pd.DataFrame())


@pytest.mark.parametrize("coach_row", [
    {
        "coach": "Prior only", "team": "BOS", "coach_cr": 8.0,
        "expected_coach_pdk": 12.0,
        "matchup_projection_available": False,
        "coach_projection_source": "prior_only",
    },
    {
        "coach": "Unverified", "team": "BOS", "coach_cr": 8.0,
        "expected_coach_pdk": 12.0,
        "matchup_projection_available": True,
        "coach_projection_source": "unverified_matchup",
    },
    {
        "coach": "Missing matchup flag", "team": "BOS", "coach_cr": 8.0,
        "expected_coach_pdk": 12.0,
        "matchup_projection_available": False,
        "coach_projection_source": "verified_matchup",
    },
])
def test_run_optimize_rejects_coaches_without_verified_projected_matchups(
    monkeypatch, coach_row
):
    def unexpected_optimizer(*args, **kwargs):
        pytest.fail("optimizer must not run without a verified coach projection")

    monkeypatch.setattr(pipeline_optimize, "optimize_top_k_lineups", unexpected_optimizer)

    with pytest.raises(RuntimeError, match="proiezione basata su un matchup Dunkest verificato"):
        pipeline_optimize.run_optimize(
            Settings.from_yaml(), pd.DataFrame(), pd.DataFrame([coach_row])
        )


def test_run_optimize_persists_verified_coach_matchup_and_scoring_evidence(monkeypatch):
    from types import SimpleNamespace

    coach = {
        "coach": "Coach A", "team": "BOS", "coach_cr": 8.0,
        "opponent": "NYK", "opponent_coach": "Coach B", "opponent_coach_cr": 7.0,
        "expected_coach_pdk": 12.0, "p10_coach_pdk": -5.0,
        "p50_coach_pdk": 12.0, "p90_coach_pdk": 25.0,
        "expected_team_pts": 116.0, "expected_opp_pts": 109.0,
        "expected_margin": 7.0, "win_probability": 0.62,
        "win_probability_before_roster_adjustment": 0.60,
        "coach_projection_source": "verified_matchup",
        "matchup_projection_available": True, "dunkest_turn": 2,
        "nba_game_id": "game-1",
    }
    solutions = [SimpleNamespace(coach="Coach A", meta={}) for _ in range(3)]
    monkeypatch.setattr(
        pipeline_optimize, "optimize_top_k_lineups",
        lambda *args, **kwargs: solutions,
    )

    result = pipeline_optimize.run_optimize(
        Settings.from_yaml(), pd.DataFrame(), pd.DataFrame([coach])
    )

    assert result[0].meta["coach_matchup"]["coach_cr"] == 8.0
    assert result[0].meta["coach_matchup"]["opponent_coach_cr"] == 7.0
    assert result[0].meta["coach_matchup"]["expected_coach_pdk"] == 12.0
    assert result[0].meta["coach_matchup"]["win_probability"] == 0.62
    assert result[0].meta["coach_matchup"]["coach_dunkest_turn"] == 2
