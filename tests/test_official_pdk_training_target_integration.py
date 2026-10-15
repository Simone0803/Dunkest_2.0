import pytest

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from dunkest.config import Settings
from dunkest.models import predictor


def test_train_models_explicit_official_target_changes_supervised_label_not_features(monkeypatch):
    x = np.arange(20, dtype=float)
    features = pd.DataFrame(
        {
            "pdk_mean_3": x,
            "expected_pdk_minutes_model": np.zeros_like(x),
            "target_pdk": 2.0 * x + 1.0,
            "target_pdk_official": -3.0 * x + 25.0,
        }
    )
    monkeypatch.setattr(predictor, "_model_zoo", lambda settings: {"ridge": Ridge(alpha=1.0)})

    proxy_models, _ = predictor.train_models(
        Settings(training_target="target_pdk"), features, target_column="target_pdk"
    )
    official_models, _ = predictor.train_models(
        Settings(training_target="target_pdk"), features, target_column="target_pdk_official"
    )

    assert proxy_models["ridge"].coef_[0] > 0
    assert official_models["ridge"].coef_[0] < 0
    assert proxy_models["_feature_cols"] == official_models["_feature_cols"]
    assert "pdk_mean_3" in proxy_models["_feature_cols"]
    assert "target_pdk_official" not in predictor.FEATURE_COLS
    assert "target_pdk" not in predictor.FEATURE_COLS


def test_train_models_accepts_positive_sample_weights_and_records_provenance(monkeypatch):
    x = np.arange(20, dtype=float)
    features = pd.DataFrame({
        "pdk_mean_3": x,
        "expected_pdk_minutes_model": np.zeros_like(x),
        "target_pdk_official": 2.0 * x + 1.0,
    })
    monkeypatch.setattr(predictor, "_model_zoo", lambda settings: {"ridge": Ridge(alpha=1.0)})
    weights = pd.Series(np.where(x <= 5, 1.25, 1.0), index=features.index)
    models, _ = predictor.train_models(
        Settings(training_target="target_pdk_official"),
        features,
        target_column="target_pdk_official",
        sample_weight=weights,
    )
    assert models["_sample_weighted_training"] is True
    assert models["_sample_weight_mean"] > 1.0


def test_train_models_rejects_nonpositive_sample_weights(monkeypatch):
    x = np.arange(20, dtype=float)
    features = pd.DataFrame({"pdk_mean_3": x, "target_pdk_official": 2.0 * x + 1.0})
    monkeypatch.setattr(predictor, "_model_zoo", lambda settings: {"ridge": Ridge(alpha=1.0)})
    with pytest.raises(ValueError, match="sample_weight values must be positive"):
        predictor.train_models(
            Settings(training_target="target_pdk_official"),
            features,
            target_column="target_pdk_official",
            sample_weight=pd.Series([0.0] * len(features), index=features.index),
        )


def test_absolute_multiseason_prediction_does_not_add_minutes_baseline_twice():
    latest = pd.DataFrame({"expected_pdk_minutes_model": [18.0, 12.0]}, index=[4, 9])
    absolute = predictor._inference_minutes_baseline({"_prediction_is_absolute": True}, latest)
    residual = predictor._inference_minutes_baseline({}, latest)
    assert absolute.tolist() == [0.0, 0.0]
    assert residual.tolist() == [18.0, 12.0]


def test_cross_fitted_calibration_uses_only_valid_oof_residuals(monkeypatch):
    rng = np.random.default_rng(42)
    x = np.arange(300, dtype=float)
    target = 10.0 + 0.03 * x + 4.0 * np.sin(x / 7.0) + rng.normal(0.0, 3.0, len(x))
    features = pd.DataFrame({
        "GAME_DATE": pd.date_range("2020-01-01", periods=len(x), freq="D"),
        "pdk_mean_3": x,
        "pdk_season_mean": 12.0 + np.sin(x / 8.0),
        "expected_pdk_minutes_model": np.zeros_like(x),
        "target_pdk_official": target,
    })
    monkeypatch.setattr(predictor, "_model_zoo", lambda settings: {"ridge": Ridge(alpha=1.0)})
    models, _ = predictor.train_models(
        Settings(training_target="target_pdk_official"),
        features,
        target_column="target_pdk_official",
    )
    diagnostics = models["_interval_diagnostics"]
    overall = next(row for row in diagnostics if row["dimension"] == "all")
    assert 0 < models["_calibration_samples"] < len(features)
    assert 0.82 <= overall["p10_coverage"] <= 0.96
    assert 0.82 <= overall["p90_coverage"] <= 0.96
