import numpy as np
import pandas as pd

from dunkest.models.predictor import (
    _fit_residual_quantiles_by_prediction_band,
    _residual_quantiles_for_predictions,
)


def test_score_band_calibration_uses_target_minus_prediction_residuals_and_shrinks():
    predictions = pd.Series([4.0] * 150 + [30.0] * 150)
    targets = pd.Series([6.0] * 150 + [27.0] * 150)
    calibration = _fit_residual_quantiles_by_prediction_band(predictions, targets)
    assert calibration["n"] == 300
    assert calibration["bands"]["<5"]["n"] == 150
    assert calibration["bands"]["25+"]["n"] == 150
    # target - prediction is +2 in the low band and -3 in the high band.
    assert calibration["bands"]["<5"]["q50"] > calibration["global"]["q50"]
    assert calibration["bands"]["25+"]["q50"] < calibration["global"]["q50"]


def test_score_band_quantile_lookup_is_index_aligned_and_falls_back_to_global():
    predictions = pd.Series([4.0, 30.0, 100.0], index=[7, 2, 9])
    targets = pd.Series([6.0, 27.0, 100.0], index=[7, 2, 9])
    calibration = _fit_residual_quantiles_by_prediction_band(predictions, targets)
    models = {
        "_residual_q10": calibration["global"]["q10"],
        "_residual_q50": calibration["global"]["q50"],
        "_residual_q90": calibration["global"]["q90"],
        "_residual_quantiles_by_prediction_band": calibration,
    }
    lookup = _residual_quantiles_for_predictions(models, predictions)
    assert list(lookup["q50"].index) == [7, 2, 9]
    assert lookup["q50"].notna().all()
    assert np.isfinite(lookup["q10"]).all()
    assert np.isfinite(lookup["q90"]).all()
