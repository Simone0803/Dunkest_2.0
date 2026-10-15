import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_dunkest_coach_official_multiplier_sensitivity_v3.py'
SPEC = importlib.util.spec_from_file_location('coach_multiplier_sensitivity_v2', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_transform_applies_official_coach_multiplier_for_positive_and_negative_scores():
    assert MODULE.transform(38.0, 5.0, True) == pytest.approx(38.0 * 0.87)
    assert MODULE.transform(-26.0, 5.0, True) == pytest.approx(-26.0 / 0.87)
    assert MODULE.transform(38.0, 5.0, False) == pytest.approx(38.0 * 1.23)
    assert MODULE.transform(-26.0, 5.0, False) == pytest.approx(-26.0 / 1.23)


def test_transform_is_neutral_when_credit_difference_is_below_one():
    assert MODULE.transform(21.0, 0.99, True) == pytest.approx(21.0)
    assert MODULE.transform(-12.0, 0.99, False) == pytest.approx(-12.0)


def test_transform_preserves_missing_predictions():
    assert MODULE.transform(float('nan'), 5.0, True) != MODULE.transform(float('nan'), 5.0, True)
