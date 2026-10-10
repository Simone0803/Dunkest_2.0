from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pulp
import copy
import numpy as np

from dunkest.config import Settings
from dunkest.optimize.objective import transfer_count
from dunkest.names import player_key
from dunkest.rules.eligibility import unavailable_mask
from dunkest.rules.roster import FORMATIONS, RosterRules, player_contribution_multiplier

STARTER_MIN_MINUTES = 18.0
SIXTH_MIN_MINUTES = 12.0
CAPTAIN_MIN_MINUTES = 22.0
MIN_STARTER_PLAY_PROB = 0.5
# A reported injury/availability doubt must never occupy one of the 10 roster
# slots, even when its conditional projection is high enough for the bench.
MIN_PLAY_PROB = 1.0
# Player outcomes share pace and game-script shocks. Use a modest common
# correlation instead of summing every individual quantile as if correlation
# were exactly one.
TEAM_PLAYER_SCORE_CORRELATION = 0.15


def _portfolio_spread(values: list[float], correlation: float = TEAM_PLAYER_SCORE_CORRELATION) -> float:
    """Combine individual one-sided spreads under a common pairwise correlation."""
    if not values:
        return 0.0
    rho = float(max(0.0, min(1.0, correlation)))
    squares = float(sum(value * value for value in values))
    common = float(sum(values)) ** 2
    return float(((1.0 - rho) * squares + rho * common) ** 0.5)


def _validate_optimizer_inputs(players: pd.DataFrame, coaches: pd.DataFrame, settings: Settings) -> None:
    player_required = {"player_name", "team", "role", "cr", "expected_pdk"}
    coach_required = {"coach", "team", "coach_cr", "expected_coach_pdk"}
    missing_players = sorted(player_required.difference(players.columns))
    if missing_players:
        raise ValueError(f"Player optimizer data missing required columns: {', '.join(missing_players)}")
    missing_coaches = sorted(coach_required.difference(coaches.columns))
    if missing_coaches:
        raise ValueError(f"Coach optimizer data missing required columns: {', '.join(missing_coaches)}")

    valid_roles = players["role"].astype(str).str.upper().isin({"G", "F", "C"})
    if not valid_roles.all():
        bad = players.loc[~valid_roles, "role"].astype(str).drop_duplicates().tolist()
        raise ValueError(f"Unsupported player role(s) for roster optimization: {', '.join(bad)}")
    player_keys = players["player_name"].map(player_key)
    duplicate_players = player_keys.eq("") | player_keys.duplicated(keep=False)
    if duplicate_players.any():
        names = players.loc[duplicate_players, "player_name"].astype(str).drop_duplicates().head(8).tolist()
        raise ValueError(
            "Player optimizer data contains blank or duplicate normalized player names: "
            f"{', '.join(names)}. Resolve identities before optimization."
        )
    for label, frame, name_column, numeric_columns in (
        ("player", players, "player_name", ("cr", "expected_pdk")),
        ("coach", coaches, "coach", ("coach_cr", "expected_coach_pdk")),
    ):
        for column in (name_column, "team"):
            missing = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
            if missing.any():
                raise ValueError(f"{label.title()} optimizer data has blank {column} values.")
        for column in numeric_columns:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
            invalid = ~np.isfinite(values)
            if invalid.any():
                names = frame.loc[invalid, name_column].astype(str).head(5).tolist()
                raise ValueError(
                    f"Non-finite {label} optimizer field {column} for: {', '.join(names)}."
                )
    if settings.optimizer_objective == "risk_adjusted":
        player_quantiles = [column for column in ("p10", "p50", "p90") if column in players]
        coach_quantiles = [column for column in ("p10_coach_pdk", "p50_coach_pdk", "p90_coach_pdk") if column in coaches]
        for label, frame, columns in (("player", players, player_quantiles), ("coach", coaches, coach_quantiles)):
            if columns and len(columns) != 3:
                raise ValueError(f"Risk-adjusted optimization requires all three {label} quantile columns.")
            if not columns:
                continue
            values = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise ValueError(f"Risk-adjusted optimization requires finite {label} quantiles.")
            if not np.all(values[:, 0] <= values[:, 1]) or not np.all(values[:, 1] <= values[:, 2]):
                raise ValueError(f"Risk-adjusted optimization requires ordered {label} quantiles P10 <= P50 <= P90.")


@dataclass
class LineupSolution:
    rank: int
    expected_team_pdk: float
    expected_player_pdk: float
    expected_coach_pdk: float
    budget_used: float
    captain: str
    coach: str
    module: str
    num_transfers: int
    players: pd.DataFrame
    overlap_with_previous: int | None = None
    p10_team: float | None = None
    p50_team: float | None = None
    p90_team: float | None = None
    raw_team_pdk: float | None = None
    transfer_malus: float = 0.0
    meta: dict = field(default_factory=dict)


def _pick_module(starter_roles: dict[int, str]) -> str:
    counts = {"G": 0, "F": 0, "C": 0}
    for role in starter_roles.values():
        counts[role] = counts.get(role, 0) + 1
    g, f, c = counts["G"], counts["F"], counts["C"]
    for fg, ff, fc in FORMATIONS:
        if (g, f, c) == (fg, ff, fc):
            return f"{fg}-{ff}-{fc}"
    return f"{g}-{f}-{c}"


def optimize_top_k_lineups(
    players: pd.DataFrame,
    coaches: pd.DataFrame,
    settings: Settings,
    current_roster: list[str] | None = None,
    current_coach: str | None = None,
    k: int | None = None,
) -> list[LineupSolution]:
    rules = RosterRules(max_from_same_team=settings.max_from_same_nba_team)
    k = settings.optimizer_top_k if k is None else int(k)
    if k < 1:
        raise ValueError("k must be a positive integer.")
    if coaches.empty:
        raise ValueError(
            "Dati coach assenti: Dunkest richiede un allenatore e il vincolo di 3 per squadra "
            "include anche il coach. Ricarica il listone/calendario coach prima di ottimizzare."
        )
    players = players.copy()
    coaches = coaches.copy()
    players["role"] = players["role"].astype(str).str.strip().str.upper()
    players["team"] = players["team"].astype(str).str.strip().str.upper()
    coaches["team"] = coaches["team"].astype(str).str.strip().str.upper()
    _validate_optimizer_inputs(players, coaches, settings)
    if coaches["coach"].map(player_key).duplicated(keep=False).any() or coaches["team"].duplicated(keep=False).any():
        raise ValueError("Coach optimizer data contains duplicate coach identities or NBA teams.")
    eligible = ~unavailable_mask(players)
    if "p_play" in players.columns:
        eligible &= pd.to_numeric(players["p_play"], errors="coerce").fillna(1.0) >= MIN_PLAY_PROB
    df = players.loc[eligible].copy()
    if "expected_min" not in df.columns:
        df["expected_min"] = 24.0
    df["expected_min"] = pd.to_numeric(df["expected_min"], errors="coerce").fillna(0.0)
    df = df[df["cr"].between(settings.min_cr, settings.max_cr)].reset_index(drop=True)
    plus = pd.to_numeric(df.get("expected_plusvalenza", pd.Series(0.0, index=df.index)), errors="coerce")
    df["expected_plusvalenza"] = plus.where(np.isfinite(plus), 0.0)
    df["_sort_name"] = df["player_name"].astype(str).str.strip().str.casefold()
    df["_sort_team"] = df["team"].astype(str).str.strip().str.upper()
    df = df.sort_values(
        ["_sort_name", "_sort_team", "role", "cr"], kind="stable"
    ).drop(columns=["_sort_name", "_sort_team"]).reset_index(drop=True)
    if len(df) < rules.total_players:
        raise ValueError(f"Not enough eligible players ({len(df)})")

    coach_df = coaches.copy()
    coach_df["_sort_coach"] = coach_df["coach"].astype(str).str.strip().str.casefold()
    coach_df["_sort_team"] = coach_df["team"].astype(str).str.strip().str.upper()
    coach_df = coach_df.sort_values(
        ["_sort_coach", "_sort_team", "coach_cr"], kind="stable"
    ).drop(columns=["_sort_coach", "_sort_team"]).reset_index(drop=True)
    coach_reference_cr = float(pd.to_numeric(coach_df["coach_cr"], errors="coerce").min())
    # Convert future CR into current PDK using the actual finite-difference
    # value of one additional CR under this slate and objective.
    shadow_price = 0.0
    shadow_price_available = False
    delta_cr = float(settings.capital_gain_budget_delta)
    if df["expected_plusvalenza"].abs().sum() > 0.0:
        base_solution, base_diag = _solve_once(
            df, coach_df, settings, rules, current_roster, current_coach, [], set(),
            set(),
            capital_gain_shadow_price=0.0,
        )
        higher_budget = copy.copy(settings)
        higher_budget.budget += delta_cr
        higher_solution, higher_diag = _solve_once(
            df, coach_df, higher_budget, rules, current_roster, current_coach, [], set(),
            set(),
            capital_gain_shadow_price=0.0,
        )
        if (base_solution is not None and higher_solution is not None
                and base_diag["status"] == higher_diag["status"] == "Optimal"):
            base_value = float(base_diag["objective_value"])
            higher_value = float(higher_diag["objective_value"])
            shadow_price = max(0.0, (higher_value - base_value) / delta_cr)
            shadow_price_available = True
    solutions: list[LineupSolution] = []
    forbidden_player_sets: list[set[int]] = []
    forbidden_captains: set[int] = set()
    forbidden_coaches: set[int] = set()

    for rank in range(1, k + 1):
        sol, solver_diagnostics = _solve_once(
            df,
            coach_df,
            settings,
            rules,
            current_roster,
            current_coach,
            forbidden_player_sets,
            forbidden_captains,
            forbidden_coaches,
            capital_gain_shadow_price=shadow_price,
        )
        if sol is None:
            if not solutions:
                raise ValueError(
                    "No feasible Dunkest lineup: check eligible players, budget, "
                    "team limits, formation and coach data. "
                    f"CBC status: {solver_diagnostics['status']} "
                    f"after {solver_diagnostics['solve_time_seconds']:.2f}s."
                )
            break
        sol.meta["solver"] = solver_diagnostics
        sol.meta["capital_gain_shadow_price"] = shadow_price
        sol.meta["budget_shadow_price"] = shadow_price
        sol.meta["budget_shadow_price_available"] = shadow_price_available
        sol.meta["capital_gain_budget_delta"] = delta_cr
        coach_index = sol.meta.get("selected_coach_index")
        if coach_index is None or not 0 <= int(coach_index) < len(coach_df):
            raise ValueError("Optimizer returned a lineup without a valid selected coach index.")
        selected_coach = coach_df.loc[int(coach_index)]
        selected_coach_cr = float(selected_coach["coach_cr"])
        sol.meta["coach_cr"] = selected_coach_cr
        sol.meta["coach_reference_cr"] = coach_reference_cr
        sol.meta["coach_opportunity_cost_pdk"] = (
            max(selected_coach_cr - coach_reference_cr, 0.0)
            * float(sol.meta["budget_shadow_price"])
            if shadow_price_available else None
        )
        sel_idx = set(sol.meta["selected_indices"])
        if solutions:
            prev = set(solutions[-1].meta["selected_indices"])
            sol.overlap_with_previous = len(sel_idx & prev)
        solutions.append(sol)
        forbidden_player_sets.append(sel_idx)
        # Each suggested roster is an alternative, so keep coach choices
        # distinct while the market contains feasible alternatives.
        forbidden_coaches.add(int(coach_index))
        captain_idx = sol.meta.get("captain_index")
        if captain_idx is not None:
            forbidden_captains.add(int(captain_idx))
        if solver_diagnostics["status"] != "Optimal":
            # A feasible timeout incumbent is usable, but subsequent solves
            # cannot be claimed to be the next-best ranked alternatives.
            break

    solutions.sort(
        key=lambda solution: float(
            solution.meta.get("solver_objective_value", solution.expected_team_pdk)
        ),
        reverse=True,
    )
    selected_coaches = [solution.coach for solution in solutions]
    if len(selected_coaches) != len(set(selected_coaches)):
        raise ValueError(
            "Optimizer returned duplicate coaches across alternative lineups; "
            "refusing to present repeated coach recommendations."
        )
    for rank, solution in enumerate(solutions, start=1):
        solution.rank = rank

    return solutions


def _solve_once(
    df: pd.DataFrame,
    coach_df: pd.DataFrame,
    settings: Settings,
    rules: RosterRules,
    current_roster: list[str] | None,
    current_coach: str | None,
    forbidden_sets: list[set[int]],
    forbidden_captains: set[int],
    forbidden_coaches: set[int],
    capital_gain_shadow_price: float = 0.0,
) -> tuple[LineupSolution | None, dict]:
    n = len(df)
    m = len(coach_df) if not coach_df.empty else 0
    current_set = {player_key(p) for p in (current_roster or []) if player_key(p)}
    current_coach_key = player_key(current_coach) if current_coach else ""

    prob = pulp.LpProblem("DunkestTeamOptimizer", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n)]
    starter = [pulp.LpVariable(f"s_{i}", cat="Binary") for i in range(n)]
    sixth = [pulp.LpVariable(f"x6_{i}", cat="Binary") for i in range(n)]
    bench = [pulp.LpVariable(f"b_{i}", cat="Binary") for i in range(n)]
    captain = [pulp.LpVariable(f"c_{i}", cat="Binary") for i in range(n)]

    y = [pulp.LpVariable(f"coach_{j}", cat="Binary") for j in range(m)] if m else []
    player_turns = (
        pd.to_numeric(df["dunkest_turn"], errors="coerce")
        if "dunkest_turn" in df.columns else pd.Series(float("nan"), index=df.index)
    )
    target_turn = settings.target_dunkest_turn

    for i in range(n):
        prob += starter[i] + sixth[i] + bench[i] == x[i]
        prob += captain[i] <= starter[i]
        if target_turn is not None and pd.notna(player_turns.loc[i]):
            if int(player_turns.loc[i]) == int(target_turn):
                # Dunkest's Turno guidance: players playing now must be put
                # on the field before tip-off. Otherwise they cannot be moved
                # from the bench after their game to replace a later player.
                # The sixth-man slot is full-value under the current rules.
                prob += bench[i] == 0
        if i in forbidden_captains:
            # Top-k options must offer different captain choices. The captain
            # remains a starter, and each subsequent MILP solve excludes all
            # previously used captains while optimizing the full objective.
            prob += captain[i] == 0
        emin_value = pd.to_numeric(df.loc[i, "expected_min"], errors="coerce")
        emin = 0.0 if pd.isna(emin_value) else float(emin_value)
        p_play = float(pd.to_numeric(df.loc[i, "p_play"], errors="coerce") if "p_play" in df.columns else 1.0)
        if pd.isna(p_play):
            p_play = 1.0
        if emin < STARTER_MIN_MINUTES or p_play < MIN_STARTER_PLAY_PROB:
            prob += starter[i] == 0
        if emin < SIXTH_MIN_MINUTES or p_play < MIN_STARTER_PLAY_PROB:
            prob += sixth[i] == 0
        if emin < CAPTAIN_MIN_MINUTES:
            prob += captain[i] == 0

    prob += pulp.lpSum(x) == rules.total_players
    prob += pulp.lpSum(x[i] for i in range(n) if df.loc[i, "role"] == "G") == rules.guards
    prob += pulp.lpSum(x[i] for i in range(n) if df.loc[i, "role"] == "F") == rules.forwards
    prob += pulp.lpSum(x[i] for i in range(n) if df.loc[i, "role"] == "C") == rules.centers
    prob += pulp.lpSum(starter) == rules.starters
    prob += pulp.lpSum(sixth) == rules.sixth_man
    prob += pulp.lpSum(bench) == rules.bench
    prob += pulp.lpSum(captain) == rules.captains

    form_vars = {
        (g, f, c): pulp.LpVariable(f"form_{g}_{f}_{c}", cat="Binary") for g, f, c in FORMATIONS
    }
    prob += pulp.lpSum(form_vars.values()) == 1
    starters_g = pulp.lpSum(starter[i] for i in range(n) if df.loc[i, "role"] == "G")
    starters_f = pulp.lpSum(starter[i] for i in range(n) if df.loc[i, "role"] == "F")
    starters_c = pulp.lpSum(starter[i] for i in range(n) if df.loc[i, "role"] == "C")
    prob += starters_g == pulp.lpSum(g * form_vars[(g, f, c)] for g, f, c in FORMATIONS)
    prob += starters_f == pulp.lpSum(f * form_vars[(g, f, c)] for g, f, c in FORMATIONS)
    prob += starters_c == pulp.lpSum(c * form_vars[(g, f, c)] for g, f, c in FORMATIONS)

    # Budget
    player_cost = pulp.lpSum(x[i] * float(df.loc[i, "cr"]) for i in range(n))
    if m:
        coach_cost = pulp.lpSum(y[j] * float(coach_df.loc[j, "coach_cr"]) for j in range(m))
        prob += pulp.lpSum(y) == 1
        for j in forbidden_coaches:
            if 0 <= j < m:
                prob += y[j] == 0
    else:
        coach_cost = 0
        y = []
    prob += player_cost + coach_cost <= float(settings.budget)

    # Max 3 from same NBA team (players + coach)
    teams = sorted(set(df["team"].astype(str)) | (set(coach_df["team"].astype(str)) if m else set()))
    for team in teams:
        player_team = pulp.lpSum(x[i] for i in range(n) if str(df.loc[i, "team"]) == team)
        coach_team = pulp.lpSum(y[j] for j in range(m) if str(coach_df.loc[j, "team"]) == team) if m else 0
        prob += player_team + coach_team <= rules.max_from_same_team

    # No-good cuts for diverse top-k
    min_different = max(0, min(rules.total_players, settings.min_different_players_top_k))
    max_overlap = rules.total_players - min_different
    for fset in forbidden_sets:
        prob += pulp.lpSum(x[i] for i in set(fset)) <= max_overlap

    objective_terms = []
    for i in range(n):
        ep = float(df.loc[i, "expected_pdk"])
        p10 = float(df.loc[i].get("p10", ep))
        p90 = float(df.loc[i].get("p90", ep))
        if settings.optimizer_objective == "risk_adjusted":
            ep = ep - settings.risk_lambda * (p90 - p10)
        mult = (
            rules.starter_multiplier * starter[i]
            + rules.sixth_man_multiplier * sixth[i]
            + rules.bench_multiplier * bench[i]
            + (rules.captain_multiplier - rules.starter_multiplier) * captain[i]
        )
        is_new = 1 if current_set and player_key(df.loc[i, "player_name"]) not in current_set else 0
        malus = settings.transfer_penalty * is_new
        objective_terms.append(mult * ep - malus * x[i])
        expected_gain = float(pd.to_numeric(df.loc[i].get("expected_plusvalenza", 0.0), errors="coerce"))
        if not np.isfinite(expected_gain):
            expected_gain = 0.0
        objective_terms.append(capital_gain_shadow_price * expected_gain * x[i])

    if m:
        for j in range(m):
            coach_ep = float(coach_df.loc[j, "expected_coach_pdk"])
            if settings.optimizer_objective == "risk_adjusted":
                coach_p10 = float(coach_df.loc[j].get("p10_coach_pdk", coach_ep))
                coach_p90 = float(coach_df.loc[j].get("p90_coach_pdk", coach_ep))
                coach_ep -= settings.risk_lambda * max(coach_p90 - coach_p10, 0.0)
            is_new_coach = (
                1
                if current_coach
                and player_key(coach_df.loc[j, "coach"]) != current_coach_key
                else 0
            )
            objective_terms.append(coach_ep * y[j] - settings.transfer_penalty * is_new_coach * y[j])

    prob += pulp.lpSum(objective_terms)
    prob.solve(
        pulp.PULP_CBC_CMD(
            msg=0,
            timeLimit=settings.optimizer_time_limit_seconds,
            gapRel=settings.optimizer_relative_gap,
        )
    )
    solver_diagnostics = {
        "solver": "CBC",
        "status": pulp.LpStatus.get(prob.status, str(prob.status)),
        "solution_status": pulp.LpSolution.get(getattr(prob, "sol_status", None), str(getattr(prob, "sol_status", None))),
        "solve_time_seconds": float(prob.solutionTime or 0.0),
        "objective_value": (
            float(pulp.value(prob.objective))
            if pulp.value(prob.objective) is not None else None
        ),
        "time_limit_seconds": settings.optimizer_time_limit_seconds,
        "relative_gap": settings.optimizer_relative_gap,
    }
    solution_status = getattr(prob, "sol_status", None)
    feasible_solution_statuses = {
        getattr(pulp, "LpSolutionOptimal", object()),
        getattr(pulp, "LpSolutionIntegerFeasible", object()),
    }
    if solver_diagnostics["status"] != "Optimal" and solution_status not in feasible_solution_statuses:
        return None, solver_diagnostics

    sel = [i for i in range(n) if pulp.value(x[i]) > 0.5]
    sel_df = df.loc[sel].copy()
    statuses = []
    starter_roles: dict[int, str] = {}
    cap_name = ""
    for i in sel:
        role = df.loc[i, "role"]
        if pulp.value(starter[i]) > 0.5:
            starter_roles[i] = role
            if pulp.value(captain[i]) > 0.5:
                statuses.append("Captain")
                cap_name = df.loc[i, "player_name"]
            else:
                statuses.append("Starter")
        elif pulp.value(sixth[i]) > 0.5:
            statuses.append("Sixth Man")
        else:
            statuses.append("Bench")
    sel_df["slot"] = statuses

    coach_name = ""
    coach_ep = 0.0
    coach_p10 = 0.0
    coach_p50 = 0.0
    coach_p90 = 0.0
    coach_cr = 0.0
    coach_matchup_available = False
    if m:
        j_sel = max(range(m), key=lambda j: pulp.value(y[j]))
        coach_name = str(coach_df.loc[j_sel, "coach"])
        coach_ep = float(coach_df.loc[j_sel, "expected_coach_pdk"])
        coach_p10 = float(coach_df.loc[j_sel].get("p10_coach_pdk", coach_ep))
        coach_p50 = float(coach_df.loc[j_sel].get("p50_coach_pdk", coach_ep))
        coach_p90 = float(coach_df.loc[j_sel].get("p90_coach_pdk", coach_ep))
        coach_cr = float(coach_df.loc[j_sel, "coach_cr"])
        raw_matchup_available = coach_df.loc[j_sel].get("matchup_projection_available", False)
        coach_matchup_available = bool(raw_matchup_available) if pd.notna(raw_matchup_available) else False

    player_ep = 0.0
    p50_sum = 0.0
    lower_spreads: list[float] = []
    upper_spreads: list[float] = []
    for i in sel:
        ep = float(df.loc[i, "expected_pdk"])
        p10 = float(df.loc[i].get("p10", ep))
        p50 = float(df.loc[i].get("p50", ep))
        p90 = float(df.loc[i].get("p90", ep))
        mult = player_contribution_multiplier(
            is_starter=pulp.value(starter[i]) > 0.5,
            is_sixth=pulp.value(sixth[i]) > 0.5,
            is_captain=pulp.value(captain[i]) > 0.5,
            rules=rules,
        )
        player_ep += ep * mult
        p50_sum += p50 * mult
        lower_spreads.append(max(p50 - p10, 0.0) * mult)
        upper_spreads.append(max(p90 - p50, 0.0) * mult)

    budget_used = float(sel_df["cr"].sum()) + coach_cr
    num_trans = transfer_count(
        sel_df["player_name"].tolist(), coach_name or None, current_roster, current_coach
    )

    lower_spreads.append(max(coach_p50 - coach_p10, 0.0))
    upper_spreads.append(max(coach_p90 - coach_p50, 0.0))
    team_p50 = p50_sum + coach_p50 - num_trans * settings.transfer_penalty
    team_p10 = team_p50 - _portfolio_spread(lower_spreads)
    team_p90 = team_p50 + _portfolio_spread(upper_spreads)
    solution = LineupSolution(
        rank=0,
        expected_team_pdk=player_ep + coach_ep - num_trans * settings.transfer_penalty,
        expected_player_pdk=player_ep,
        expected_coach_pdk=coach_ep,
        budget_used=budget_used,
        captain=cap_name,
        coach=coach_name,
        module=_pick_module(starter_roles),
        num_transfers=num_trans,
        players=sel_df,
        p10_team=team_p10,
        p50_team=team_p50,
        p90_team=team_p90,
        raw_team_pdk=player_ep + coach_ep,
        transfer_malus=num_trans * settings.transfer_penalty,
        meta={
            "selected_indices": list(sel),
            "selected_coach_index": int(j_sel) if m else None,
            "captain_index": next(
                (i for i in sel if pulp.value(captain[i]) > 0.5), None
            ),
            "solver_objective_value": solver_diagnostics["objective_value"],
            "expected_budget_gain": float(pd.to_numeric(sel_df["expected_plusvalenza"], errors="coerce").fillna(0.0).sum()),
            "future_budget_value_pdk": float(capital_gain_shadow_price * pd.to_numeric(sel_df["expected_plusvalenza"], errors="coerce").fillna(0.0).sum()),
            "capital_gain_shadow_price": float(capital_gain_shadow_price),
            "coach_matchup_available": coach_matchup_available,
            "initial_dunkest_turn": target_turn,
        },
    )
    validate_solution(
        solution,
        coaches=coach_df,
        settings=settings,
        current_roster=current_roster,
        current_coach=current_coach,
        rules=rules,
    )
    return solution, solver_diagnostics


def validate_solution(
    solution: LineupSolution,
    coaches: pd.DataFrame,
    settings: Settings,
    current_roster: list[str] | None = None,
    current_coach: str | None = None,
    rules: RosterRules | None = None,
) -> None:
    """Validate a lineup independently of the MILP constraints."""
    rules = rules or RosterRules(max_from_same_team=settings.max_from_same_nba_team)
    selected = solution.players
    errors: list[str] = []
    if unavailable_mask(selected).any():
        errors.append("lineup contains a confirmed unavailable player")
    if "p_play" in selected:
        play_probabilities = pd.to_numeric(selected["p_play"], errors="coerce").fillna(1.0)
        if play_probabilities.lt(MIN_PLAY_PROB).any():
            errors.append("lineup contains a player with an injury/availability doubt")
    if len(selected) != rules.total_players:
        errors.append(f"roster size {len(selected)} != {rules.total_players}")
    if selected["player_name"].map(player_key).duplicated().any():
        errors.append("duplicate player identity")
    roles = selected["role"].astype(str).str.strip().str.upper()
    for role, count in (("G", rules.guards), ("F", rules.forwards), ("C", rules.centers)):
        if int(roles.eq(role).sum()) != count:
            errors.append(f"invalid {role} count")
    slots = selected["slot"].astype(str)
    if int(slots.isin({"Starter", "Captain"}).sum()) != rules.starters:
        errors.append("invalid starter count")
    if int(slots.eq("Sixth Man").sum()) != rules.sixth_man:
        errors.append("invalid sixth-man count")
    if int(slots.eq("Bench").sum()) != rules.bench:
        errors.append("invalid bench count")
    captains = selected.loc[slots.eq("Captain"), "player_name"].astype(str).tolist()
    if len(captains) != rules.captains or captains != [solution.captain]:
        errors.append("captain slot and captain field disagree")
    if solution.module not in {f"{g}-{f}-{c}" for g, f, c in FORMATIONS}:
        errors.append(f"invalid formation {solution.module!r}")
    starter_roles = roles.loc[slots.isin({"Starter", "Captain"})].value_counts().to_dict()
    expected_module = f"{starter_roles.get('G', 0)}-{starter_roles.get('F', 0)}-{starter_roles.get('C', 0)}"
    if solution.module != expected_module:
        errors.append("reported module does not match starter positions")
    player_team_counts = selected.assign(
        _team=selected["team"].astype(str).str.strip().str.upper()
    ).groupby("_team").size()
    if (player_team_counts > rules.max_from_same_team).any():
        errors.append("player team limit exceeded")

    coach_rows = coaches.loc[coaches["coach"].astype(str).eq(solution.coach)]
    if len(coach_rows) != 1:
        errors.append("selected coach is absent or ambiguous")
        coach_row = None
    else:
        coach_row = coach_rows.iloc[0]
        coach_team = str(coach_row["team"]).strip().upper()
        team_counts = selected.assign(
            _team=selected["team"].astype(str).str.strip().str.upper()
        ).groupby("_team").size()
        if int(team_counts.get(coach_team, 0)) + 1 > rules.max_from_same_team:
            errors.append("player and coach team limit exceeded")
        cost = float(pd.to_numeric(selected["cr"], errors="coerce").sum()) + float(coach_row["coach_cr"])
        if cost > settings.budget + 1e-6:
            errors.append("budget exceeded")
        if abs(cost - solution.budget_used) > 1e-6:
            errors.append("reported budget does not match selected entities")

    raw_player_score = 0.0
    for _, player in selected.iterrows():
        slot = str(player["slot"])
        multiplier = player_contribution_multiplier(
            is_starter=slot in {"Starter", "Captain"},
            is_sixth=slot == "Sixth Man",
            is_captain=slot == "Captain",
            rules=rules,
        )
        raw_player_score += float(player["expected_pdk"]) * multiplier
    if abs(raw_player_score - solution.expected_player_pdk) > 1e-6:
        errors.append("reported player score does not match slots and multipliers")
    if coach_row is not None:
        coach_score = float(coach_row["expected_coach_pdk"])
        transfers = transfer_count(
            selected["player_name"].astype(str).tolist(),
            solution.coach,
            current_roster,
            current_coach,
        )
        expected_net = raw_player_score + coach_score - transfers * settings.transfer_penalty
        expected_malus = transfers * settings.transfer_penalty
        if solution.raw_team_pdk is not None and abs(
            raw_player_score + coach_score - solution.raw_team_pdk
        ) > 1e-6:
            errors.append("reported gross team score does not match player and coach projections")
        if abs(solution.transfer_malus - expected_malus) > 1e-6:
            errors.append("reported transfer malus is inconsistent")
        if abs(expected_net - solution.expected_team_pdk) > 1e-6:
            errors.append("reported team score does not match player, coach and transfer accounting")
        if transfers != solution.num_transfers:
            errors.append("reported transfer count is inconsistent")
        recomputed_objective = 0.0
        current_keys = {player_key(name) for name in (current_roster or []) if player_key(name)}
        for _, player in selected.iterrows():
            score = float(player["expected_pdk"])
            if settings.optimizer_objective == "risk_adjusted":
                score -= settings.risk_lambda * (
                    float(player.get("p90", score)) - float(player.get("p10", score))
                )
            slot = str(player["slot"])
            multiplier = player_contribution_multiplier(
                slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain", rules
            )
            recomputed_objective += score * multiplier
            gain = pd.to_numeric(player.get("expected_plusvalenza", 0.0), errors="coerce")
            if pd.notna(gain):
                recomputed_objective += float(solution.meta.get("capital_gain_shadow_price", 0.0)) * float(gain)
            if current_keys and player_key(player["player_name"]) not in current_keys:
                recomputed_objective -= settings.transfer_penalty
        objective_coach = coach_score
        if settings.optimizer_objective == "risk_adjusted":
            objective_coach -= settings.risk_lambda * (
                float(coach_row.get("p90_coach_pdk", coach_score))
                - float(coach_row.get("p10_coach_pdk", coach_score))
            )
        if current_coach and player_key(current_coach) != player_key(solution.coach):
            objective_coach -= settings.transfer_penalty
        recomputed_objective += objective_coach
        selected_gain = float(
            pd.to_numeric(selected.get("expected_plusvalenza", pd.Series(0.0, index=selected.index)), errors="coerce")
            .fillna(0.0).sum()
        )
        if abs(float(solution.meta.get("expected_budget_gain", selected_gain)) - selected_gain) > 1e-6:
            errors.append("reported expected budget gain does not match selected players")
        shadow_price = float(solution.meta.get("capital_gain_shadow_price", 0.0))
        expected_future_value = shadow_price * selected_gain
        if abs(float(solution.meta.get("future_budget_value_pdk", expected_future_value)) - expected_future_value) > 1e-6:
            errors.append("reported future budget value does not match shadow-price calculation")
        solver_objective = solution.meta.get("solver_objective_value")
        if solver_objective is not None and abs(recomputed_objective - float(solver_objective)) > 1e-5:
            errors.append("MILP objective does not match independently recomputed objective")
        solution.meta["validation"] = {
            "valid": not errors,
            "recomputed_player_score": raw_player_score,
            "recomputed_net_score": expected_net,
            "recomputed_optimizer_objective": recomputed_objective,
            "budget_used": solution.budget_used,
            "transfers": transfers,
        }
    if errors:
        raise ValueError("Invalid optimizer solution: " + "; ".join(errors))
