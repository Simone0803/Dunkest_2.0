from __future__ import annotations

from dataclasses import dataclass, field, fields
from math import isfinite
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    season: str = "2026-27"
    season_id: str = "26"
    target_gameweek: int = 1
    target_dunkest_turn: int | None = None
    budget: float = 95.0
    min_cr: float = 4.0
    max_cr: float = 35.0
    transfer_penalty: float = 5.0
    max_from_same_nba_team: int = 3
    model_type: str = "ensemble"
    # auto prefers official Dunkest PDK labels when at least 1,000 verified targets exist.
    training_target: str = "auto"
    rolling_windows: list[int] = field(default_factory=lambda: [3, 5, 10, 15])
    use_betting_lines: bool = False
    use_injuries: bool = True
    use_matchup: bool = True
    use_coach_model: bool = True
    use_schedule: bool = True
    data_dir: str = "data"
    nba_season_start: str = "2026-10-20"
    nba_season_end: str = "2027-06-30"
    dunkest_api_base: str = "https://www.dunkest.com/api"
    http_timeout: float = 30.0
    http_retries: int = 3
    market_cache_max_age_hours: float = 6.0
    optimizer_top_k: int = 3
    optimizer_starter_min_minutes: float = 18.0
    optimizer_sixth_min_minutes: float = 12.0
    optimizer_captain_min_minutes: float = 22.0
    optimizer_min_starter_play_probability: float = 0.5
    # When false, optimize the roster/slots without assigning a captain bonus.
    # Captain choice is manual and the displayed expected score excludes +50%.
    optimize_captain: bool = True
    # Top-k means the best distinct player rosters. Larger values are an
    # explicit diversification constraint and can reduce the achievable score.
    min_different_players_top_k: int = 1
    optimizer_objective: str = "expected_value"
    # Historical seasons (ending before the active season) used to calibrate
    # Dunkest's score/starting-CR to value-change relationship.
    capital_gain_history_seasons: int = 5
    capital_gain_budget_delta: float = 1.0
    optimizer_time_limit_seconds: float = 30.0
    optimizer_relative_gap: float = 0.0
    risk_lambda: float = 0.15
    optimizer_risk_lambda_grid: list[float] = field(
        default_factory=lambda: [0.05, 0.10, 0.15, 0.25, 0.40]
    )
    random_state: int = 42
    max_player_log_entries: int = 0
    use_nba_api_logs: bool = True
    allow_synthetic_logs: bool = False
    impute_missing_cr: bool = False
    feature_season: str = "2025-26"
    # Opening-round supervised training uses certified Dunkest labels from 2020/21–2024/25.
    opening_multiseason_training: bool = True
    opening_prior_season_id: str = "25"
    opening_use_pdk_cr_proxy: bool = False
    opening_pdk_cr_scale: float = 2.75
    # Conservative weight for the separately validated historical game-level PDK model.
    historical_pdk_blend_weight: float = 0.20
    opening_player_names: list[str] = field(default_factory=list)
    current_roster: list[str] = field(default_factory=list)
    current_coach: str | None = None

    def __post_init__(self) -> None:
        self.model_type = self.model_type.strip().casefold()
        self.training_target = self.training_target.strip().casefold()
        if self.training_target not in {"auto", "target_pdk", "target_pdk_official"}:
            raise ValueError("training_target must be one of: auto, target_pdk, target_pdk_official.")
        self.optimizer_objective = self.optimizer_objective.strip().casefold()
        if self.optimizer_objective not in {"expected_value", "risk_adjusted"}:
            raise ValueError(
                "optimizer_objective must be either 'expected_value' or 'risk_adjusted'."
            )
        if not isfinite(self.budget) or self.budget <= 0:
            raise ValueError("budget must be finite and positive.")
        if not isfinite(self.min_cr) or not isfinite(self.max_cr) or self.min_cr > self.max_cr:
            raise ValueError("min_cr and max_cr must be finite and min_cr <= max_cr.")
        if not isfinite(self.transfer_penalty) or self.transfer_penalty < 0:
            raise ValueError("transfer_penalty must be finite and nonnegative.")
        if self.max_from_same_nba_team < 1:
            raise ValueError("max_from_same_nba_team must be positive.")
        if not isfinite(self.historical_pdk_blend_weight) or not 0.0 <= self.historical_pdk_blend_weight <= 1.0:
            raise ValueError("historical_pdk_blend_weight must be finite and between 0 and 1.")
        if not isfinite(self.risk_lambda) or self.risk_lambda < 0:
            raise ValueError("risk_lambda must be finite and nonnegative.")
        if not self.rolling_windows or any(window < 1 for window in self.rolling_windows):
            raise ValueError("rolling_windows must contain positive integers.")
        if self.http_timeout <= 0 or not isfinite(self.http_timeout):
            raise ValueError("http_timeout must be finite and positive.")
        if self.http_retries < 1:
            raise ValueError("http_retries must be positive.")
        if self.model_type != "ensemble":
            raise ValueError(
                f"Unsupported model_type {self.model_type!r}; only 'ensemble' is implemented."
            )
        if self.use_betting_lines:
            raise ValueError("use_betting_lines is not supported by the current prediction pipeline.")
        if self.optimizer_time_limit_seconds <= 0:
            raise ValueError("optimizer_time_limit_seconds must be positive.")
        if self.market_cache_max_age_hours <= 0:
            raise ValueError("market_cache_max_age_hours must be positive.")
        if self.optimizer_top_k < 1:
            raise ValueError("optimizer_top_k must be positive.")
        for name in ("optimizer_starter_min_minutes", "optimizer_sixth_min_minutes", "optimizer_captain_min_minutes"):
            value = getattr(self, name)
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and nonnegative.")
        if not isfinite(self.optimizer_min_starter_play_probability) or not 0.0 <= self.optimizer_min_starter_play_probability <= 1.0:
            raise ValueError("optimizer_min_starter_play_probability must be in [0, 1].")
        if not 1 <= self.min_different_players_top_k <= 10:
            raise ValueError("min_different_players_top_k must be between 1 and 10.")
        if not 0.0 <= self.optimizer_relative_gap < 1.0:
            raise ValueError("optimizer_relative_gap must be in [0, 1).")
        if self.capital_gain_history_seasons < 1:
            raise ValueError("capital_gain_history_seasons must be positive.")
        if self.capital_gain_budget_delta <= 0.0:
            raise ValueError("capital_gain_budget_delta must be positive.")
        if self.target_dunkest_turn is not None and self.target_dunkest_turn < 1:
            raise ValueError("target_dunkest_turn must be a positive Dunkest turn number.")
        if any(not isfinite(value) or value < 0.0 for value in self.optimizer_risk_lambda_grid):
            raise ValueError("optimizer_risk_lambda_grid values must be finite and nonnegative.")

    @property
    def root(self) -> Path:
        return _repo_root()

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else self.root / p

    @classmethod
    def from_yaml(cls, path: Path | None = None, **overrides: Any) -> "Settings":
        path = path or _repo_root() / "config" / "default.yaml"
        data: dict[str, Any] = {}
        if path.exists():
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration must be a YAML mapping: {path}")
        data.update(overrides)
        # Fail fast on misspelled settings instead of silently running with
        # defaults. `season_opener` is a legacy nested section consumed by the
        # season-opener command; all other top-level keys must map to Settings.
        allowed = {item.name for item in fields(cls)} | {"rolling_windows", "season_opener"}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(
                f"Unknown configuration key(s) in {path}: {', '.join(unknown)}"
            )
        opener = data.get("season_opener") or {}
        rolling = data.get("rolling_windows", [3, 5, 10, 15])
        return cls(
            season=str(data.get("season", cls.season)),
            season_id=str(data.get("season_id", cls.season_id)),
            target_gameweek=int(data.get("target_gameweek", cls.target_gameweek)),
            target_dunkest_turn=(
                int(data["target_dunkest_turn"])
                if data.get("target_dunkest_turn") is not None else None
            ),
            budget=float(data.get("budget", cls.budget)),
            min_cr=float(data.get("min_cr", cls.min_cr)),
            max_cr=float(data.get("max_cr", cls.max_cr)),
            transfer_penalty=float(data.get("transfer_penalty", cls.transfer_penalty)),
            max_from_same_nba_team=int(
                data.get("max_from_same_nba_team", cls.max_from_same_nba_team)
            ),
            model_type=str(data.get("model_type", cls.model_type)),
            training_target=str(data.get("training_target", cls.training_target)),
            rolling_windows=[int(x) for x in rolling],
            use_betting_lines=bool(data.get("use_betting_lines", cls.use_betting_lines)),
            use_injuries=bool(data.get("use_injuries", cls.use_injuries)),
            use_matchup=bool(data.get("use_matchup", cls.use_matchup)),
            use_coach_model=bool(data.get("use_coach_model", cls.use_coach_model)),
            use_schedule=bool(data.get("use_schedule", cls.use_schedule)),
            data_dir=str(data.get("data_dir", cls.data_dir)),
            nba_season_start=str(data.get("nba_season_start", cls.nba_season_start)),
            nba_season_end=str(data.get("nba_season_end", cls.nba_season_end)),
            dunkest_api_base=str(data.get("dunkest_api_base", cls.dunkest_api_base)),
            http_timeout=float(data.get("http_timeout", cls.http_timeout)),
            http_retries=int(data.get("http_retries", cls.http_retries)),
            market_cache_max_age_hours=float(
                data.get("market_cache_max_age_hours", cls.market_cache_max_age_hours)
            ),
            optimizer_top_k=int(data.get("optimizer_top_k", cls.optimizer_top_k)),
            optimizer_starter_min_minutes=float(data.get("optimizer_starter_min_minutes", cls.optimizer_starter_min_minutes)),
            optimizer_sixth_min_minutes=float(data.get("optimizer_sixth_min_minutes", cls.optimizer_sixth_min_minutes)),
            optimizer_captain_min_minutes=float(data.get("optimizer_captain_min_minutes", cls.optimizer_captain_min_minutes)),
            optimizer_min_starter_play_probability=float(data.get("optimizer_min_starter_play_probability", cls.optimizer_min_starter_play_probability)),
            optimize_captain=bool(data.get("optimize_captain", cls.optimize_captain)),
            min_different_players_top_k=int(
                data.get("min_different_players_top_k", cls.min_different_players_top_k)
            ),
            optimizer_objective=str(
                data.get("optimizer_objective", cls.optimizer_objective)
            ),
            capital_gain_history_seasons=int(data.get("capital_gain_history_seasons", cls.capital_gain_history_seasons)),
            capital_gain_budget_delta=float(data.get("capital_gain_budget_delta", cls.capital_gain_budget_delta)),
            optimizer_time_limit_seconds=float(
                data.get("optimizer_time_limit_seconds", cls.optimizer_time_limit_seconds)
            ),
            optimizer_relative_gap=float(
                data.get("optimizer_relative_gap", cls.optimizer_relative_gap)
            ),
            risk_lambda=float(data.get("risk_lambda", cls.risk_lambda)),
            optimizer_risk_lambda_grid=[
                float(value)
                for value in data.get(
                    "optimizer_risk_lambda_grid", [0.05, 0.10, 0.15, 0.25, 0.40]
                )
            ],
            random_state=int(data.get("random_state", cls.random_state)),
            max_player_log_entries=int(
                data.get("max_player_log_entries", cls.max_player_log_entries)
            ),
            use_nba_api_logs=bool(data.get("use_nba_api_logs", cls.use_nba_api_logs)),
            allow_synthetic_logs=bool(
                data.get("allow_synthetic_logs", cls.allow_synthetic_logs)
            ),
            impute_missing_cr=bool(data.get("impute_missing_cr", cls.impute_missing_cr)),
            feature_season=str(opener.get("prior_season", data.get("feature_season", cls.feature_season))),
            opening_multiseason_training=bool(data.get("opening_multiseason_training", cls.opening_multiseason_training)),
            opening_prior_season_id=str(data.get("opening_prior_season_id", cls.opening_prior_season_id)),
            opening_use_pdk_cr_proxy=bool(
                opener.get("use_pdk_cr_proxy", data.get("opening_use_pdk_cr_proxy", cls.opening_use_pdk_cr_proxy))
            ),
            opening_pdk_cr_scale=float(
                opener.get("pdk_cr_scale", data.get("opening_pdk_cr_scale", cls.opening_pdk_cr_scale))
            ),
            historical_pdk_blend_weight=float(
                data.get("historical_pdk_blend_weight", cls.historical_pdk_blend_weight)
            ),
            opening_player_names=list(data.get("opening_player_names", [])),
            current_roster=list(data.get("current_roster", [])),
            current_coach=data.get("current_coach"),
        )


def settings_for_season_opener(base: Settings | None = None, **overrides: Any) -> Settings:
    """Preset: G1 nuova squadra, 95 CR, nessun malus, dati forma anno precedente."""
    s = base or Settings.from_yaml()
    s.target_gameweek = 1
    s.budget = 95.0
    s.transfer_penalty = 0.0
    s.current_roster = []
    s.current_coach = None
    s.impute_missing_cr = False
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def load_roster_yaml(path: Path) -> tuple[list[str], str | None]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    players = list(data.get("players") or [])
    coach = data.get("coach")
    return players, coach
