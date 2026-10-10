from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestReport:
    average_team_score: float
    median_team_score: float
    best_of_3_realized: float
    regret_vs_ex_post: float
    top1_hit_rate: float
    top3_hit_rate: float
    captain_accuracy: float
    coach_accuracy: float
    average_transfers: float
    rows: list[dict] = field(default_factory=list)
    average_player_score: float = float("nan")
    median_player_score: float = float("nan")
    best_of_3_player_score: float = float("nan")
    regret_vs_ex_post_player_score: float = float("nan")


def compute_backtest_metrics(results: pd.DataFrame) -> BacktestReport:
    if results.empty:
        unavailable = float("nan")
        return BacktestReport(*([unavailable] * 9))

    # Rank 1 is the deployed recommendation. Do not average its score together
    # with alternative lineups; report best-of-k separately.
    ranked = results.copy()
    if "rank" in ranked.columns:
        ranked["_rank_numeric"] = pd.to_numeric(ranked["rank"], errors="coerce")
        rank1 = ranked.loc[ranked["_rank_numeric"].eq(1)].copy()
    else:
        rank1 = ranked.copy()

    team_scored = rank1.dropna(subset=["realized_team_score"]) if "realized_team_score" in rank1 else pd.DataFrame()
    avg = float(team_scored["realized_team_score"].mean()) if not team_scored.empty else float("nan")
    med = float(team_scored["realized_team_score"].median()) if not team_scored.empty else float("nan")
    scored_all = results.dropna(subset=["realized_team_score"]) if "realized_team_score" in results else pd.DataFrame()
    best3 = (
        float(scored_all.groupby("gameweek")["realized_team_score"].max().mean())
        if not scored_all.empty else float("nan")
    )
    comparable = (
        rank1.dropna(subset=["ex_post_optimum", "realized_team_score"])
        if {"ex_post_optimum", "realized_team_score"}.issubset(rank1.columns)
        else pd.DataFrame()
    )
    regret = (
        float((comparable["ex_post_optimum"] - comparable["realized_team_score"]).mean())
        if not comparable.empty else float("nan")
    )

    cap_hits = pd.to_numeric(rank1.get("captain_hit", pd.Series(dtype=float)), errors="coerce").dropna()
    coach_hits = pd.to_numeric(rank1.get("coach_hit", pd.Series(dtype=float)), errors="coerce").dropna()
    cap_acc = float(cap_hits.mean()) if not cap_hits.empty else float("nan")
    coach_acc = float(coach_hits.mean()) if not coach_hits.empty else float("nan")
    transfer_values = pd.to_numeric(rank1.get("num_transfers", pd.Series(dtype=float)), errors="coerce").dropna()
    transfers = float(transfer_values.mean()) if not transfer_values.empty else float("nan")

    player_scored = rank1.dropna(subset=["realized_player_score"]) if "realized_player_score" in rank1 else pd.DataFrame()
    avg_player = float(player_scored["realized_player_score"].mean()) if not player_scored.empty else float("nan")
    median_player = float(player_scored["realized_player_score"].median()) if not player_scored.empty else float("nan")
    scored_players_all = results.dropna(subset=["realized_player_score"]) if "realized_player_score" in results else pd.DataFrame()
    best3_player = (
        float(scored_players_all.groupby("gameweek")["realized_player_score"].max().mean())
        if not scored_players_all.empty else float("nan")
    )
    player_comparable = (
        rank1.dropna(subset=["ex_post_player_optimum", "realized_player_score"])
        if {"ex_post_player_optimum", "realized_player_score"}.issubset(rank1.columns)
        else pd.DataFrame()
    )
    player_regret = (
        float((player_comparable["ex_post_player_optimum"] - player_comparable["realized_player_score"]).mean())
        if not player_comparable.empty else float("nan")
    )

    top1_hits: list[float] = []
    top3_hits: list[float] = []
    if "ex_post_player_optimum" in scored_players_all and "gameweek" in scored_players_all:
        for _, week in scored_players_all.groupby("gameweek"):
            optimum_values = pd.to_numeric(week["ex_post_player_optimum"], errors="coerce").dropna()
            if optimum_values.empty:
                continue
            optimum = float(optimum_values.max())
            tolerance = 1e-6
            first = week.loc[
                pd.to_numeric(week.get("rank"), errors="coerce").eq(1),
                "realized_player_score",
            ]
            first = pd.to_numeric(first, errors="coerce").dropna()
            if not first.empty:
                top1_hits.append(float(float(first.iloc[0]) >= optimum - tolerance))
            top3_hits.append(
                float(float(pd.to_numeric(week["realized_player_score"], errors="coerce").max()) >= optimum - tolerance)
            )

    return BacktestReport(
        average_team_score=avg,
        median_team_score=med,
        best_of_3_realized=best3,
        regret_vs_ex_post=regret,
        top1_hit_rate=float(np.mean(top1_hits)) if top1_hits else float("nan"),
        top3_hit_rate=float(np.mean(top3_hits)) if top3_hits else float("nan"),
        captain_accuracy=cap_acc,
        coach_accuracy=coach_acc,
        average_transfers=transfers,
        rows=results.to_dict(orient="records"),
        average_player_score=avg_player,
        median_player_score=median_player,
        best_of_3_player_score=best3_player,
        regret_vs_ex_post_player_score=player_regret,
    )
