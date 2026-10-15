import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_dunkest_coach_score_forecast_monte_carlo_walk_forward_v3.py'
SPEC = importlib.util.spec_from_file_location('coach_mc_walk_forward_v3', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_monte_carlo_seed_is_deterministic_for_same_matchup():
    assert MODULE.stable_seed('2025-26-0022500001-mc-coach-v1') == MODULE.stable_seed('2025-26-0022500001-mc-coach-v1')


def test_team_score_standard_deviation_is_shrunk_and_bounded():
    assert MODULE._team_sd([112.0], 12.0) == pytest.approx(12.0)
    value = MODULE._team_sd([80.0, 160.0, 85.0], 12.0)
    assert 8.0 <= value <= 18.0
