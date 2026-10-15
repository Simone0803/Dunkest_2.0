import numpy as np
import pandas as pd

from dunkest.names import player_key, player_surname


def test_player_key_handles_missing_scalar_values():
    for value in (None, pd.NA, np.nan, float("nan")):
        assert player_key(value) == ""
        assert player_surname(value) == ""


def test_player_key_keeps_existing_normalization():
    assert player_key("Nikola Jokić") == "nikola jokic"
    assert player_key("Gary Payton II") == "gary payton"
