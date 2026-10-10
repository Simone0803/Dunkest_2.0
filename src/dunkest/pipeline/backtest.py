from __future__ import annotations

from dunkest.backtest.walk_forward import run_walk_forward_backtest
from dunkest.config import Settings


def run_backtest(settings: Settings, from_gw: int, to_gw: int):
    return run_walk_forward_backtest(settings, from_gw, to_gw)
