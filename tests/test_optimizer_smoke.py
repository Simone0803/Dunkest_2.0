import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.optimize.milp import optimize_top_k_lineups, validate_solution


def _sample_players(n=40):
    role_block = ["G"] * 16 + ["F"] * 16 + ["C"] * 8
    roles = (role_block * ((n + len(role_block) - 1) // len(role_block)))[:n]
    return pd.DataFrame(
        {
            "player_name": [f"P{i}" for i in range(n)],
            "team": [f"T{i % 10}" for i in range(n)],
            "role": roles[:n],
            "cr": [8.0 + (i % 5) for i in range(n)],
            "expected_pdk": [20 + (i % 7) for i in range(n)],
            "p10": [15 + (i % 5) for i in range(n)],
            "p50": [20 + (i % 7) for i in range(n)],
            "p90": [28 + (i % 6) for i in range(n)],
            "p_play": [1.0] * n,
        }
    )


def test_top3_lineups_smoke():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    coaches = pd.DataFrame(
        {
            "coach": [f"C{i}" for i in range(5)],
            "team": [f"T{i}" for i in range(5)],
            "coach_cr": [7.0, 8.0, 9.0, 6.0, 10.0],
            "expected_coach_pdk": [5, 6, 7, 4, 8],
        },
        index=[10, 20, 30, 40, 50],
    )
    sols = optimize_top_k_lineups(players, coaches, settings, k=3)
    assert len(sols) == 3
    for sol in sols:
        assert len(sol.players) == 10
        assert sol.players["role"].value_counts().to_dict() == {"G": 4, "F": 4, "C": 2}
        assert sol.players["slot"].value_counts().to_dict() == {
            "Starter": 4, "Captain": 1, "Sixth Man": 1, "Bench": 4
        }
        assert sol.budget_used <= settings.budget
        team_counts = sol.players.groupby("team").size().to_dict()
        coach_team = coaches.set_index("coach").loc[sol.coach, "team"]
        assert team_counts.get(coach_team, 0) + 1 <= 3
        assert len(sol.captain) > 0
    scores = [solution.expected_team_pdk for solution in sols]
    assert scores == sorted(scores, reverse=True)
    objectives = [solution.meta["solver_objective_value"] for solution in sols]
    assert objectives == sorted(objectives, reverse=True)
    for solution in sols:
        assert solution.meta["validation"]["valid"] is True
        assert solution.raw_team_pdk == pytest.approx(
            solution.expected_team_pdk + solution.transfer_malus
        )
    roster_keys = [frozenset(solution.players["player_name"]) for solution in sols]
    assert len(set(roster_keys)) == len(roster_keys)
    assert len({solution.captain for solution in sols}) == len(sols)
    assert len({solution.coach for solution in sols}) == len(sols)


def test_unavailable_players_are_removed_even_if_projection_says_available():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    players["lineup_group"] = "PANCHINA"
    players["status"] = "AVAILABLE"
    players.loc[0, "lineup_group"] = "INDISPONIBILI"
    players.loc[0, "status"] = "OUT"
    # Deliberately conflict with the availability metadata: the explicit
    # unavailable list must remain authoritative at the optimizer boundary.
    players.loc[0, "p_play"] = 1.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })
    solutions = optimize_top_k_lineups(players, coaches, settings, k=1)
    assert solutions
    assert "P0" not in set(solutions[0].players["player_name"])


def test_current_turn_players_are_not_left_on_the_half_value_bench():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.target_dunkest_turn = 1
    players = _sample_players(40)
    players["dunkest_turn"] = 2
    players.loc[:5, "dunkest_turn"] = 1
    players.loc[:5, "expected_pdk"] = 100.0
    players["expected_min"] = 24.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    current_turn = solution.players.loc[solution.players["dunkest_turn"].eq(1)]
    assert not current_turn["slot"].eq("Bench").any()


def test_whole_gameweek_roster_keeps_first_turn_players_off_the_bench():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.target_dunkest_turn = None
    players = _sample_players(40)
    players["dunkest_turn"] = 2
    players.loc[:5, "dunkest_turn"] = 1
    players.loc[:5, "expected_pdk"] = 100.0
    players["expected_min"] = 24.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    first_turn = solution.players.loc[solution.players["dunkest_turn"].eq(1)]
    assert not first_turn["slot"].eq("Bench").any()


def test_whole_gameweek_optimizes_legal_lineups_for_each_player_turn():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.target_dunkest_turn = None
    players = _sample_players(40)
    players["dunkest_turn"] = [1 if i % 5 == 0 else 2 if i % 5 in {1, 2, 3} else 3 for i in range(40)]
    players["expected_min"] = 24.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert solution.meta["dynamic_turn_mode"] is True
    assert solution.module == "dinamico-per-turno"
    assert solution.meta["turn_lineups"].keys() == {"1", "2", "3"}
    captain_schedule = solution.meta["captain_schedule"]
    assert len(captain_schedule) == 1
    captain_turn, initial_captain = next(iter(captain_schedule.items()))
    assert solution.captain == initial_captain
    assert solution.players.set_index("player_name").loc[initial_captain, "dunkest_turn"] == int(captain_turn)
    assert solution.meta["turn_lineups"][captain_turn]["slots"][initial_captain] == "Captain"
    assert sum(
        slot == "Captain"
        for lineup in solution.meta["turn_lineups"].values()
        for slot in lineup["slots"].values()
    ) == 1
    for turn, lineup in solution.meta["turn_lineups"].items():
        slots = pd.Series(lineup["slots"], dtype=str)
        assert int(slots.isin({"Starter", "Captain"}).sum()) == 5
        assert int(slots.eq("Sixth Man").sum()) == 1
        assert int(slots.eq("Bench").sum()) == 4
        assert lineup["module"] in {"2-2-1", "2-1-2", "1-3-1", "3-1-1", "1-2-2"}
    for name, row in solution.players.set_index("player_name").iterrows():
        assert row["slot"] == solution.meta["turn_lineups"][str(int(row["dunkest_turn"]))]["slots"][name]
        own_turn = int(row["dunkest_turn"])
        own_slot = row["slot"]
        previous_slot = own_slot
        for later_turn in (turn for turn in (1, 2, 3) if turn > own_turn):
            later_slot = solution.meta["turn_lineups"][str(later_turn)]["slots"][name]
            assert not (previous_slot == "Bench" and later_slot in {"Starter", "Captain", "Sixth Man"})
            previous_slot = later_slot
        final_slot = solution.meta["turn_lineups"]["3"]["slots"][name]
        expected_multiplier = 0.5 + 0.5 * float(own_slot == "Sixth Man" or final_slot in {"Starter", "Captain", "Sixth Man"})
        expected_multiplier += 0.5 * float(own_slot == "Captain" and final_slot in {"Starter", "Captain", "Sixth Man"})
        assert row["score_multiplier"] == pytest.approx(expected_multiplier)
    assert solution.expected_player_pdk == pytest.approx(
        (solution.players["expected_pdk"] * solution.players["score_multiplier"]).sum()
    )
    assert solution.meta["validation"]["valid"] is True


def test_dynamic_lineup_validator_rejects_post_game_slot_changes():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.target_dunkest_turn = None
    players = _sample_players(40)
    players["dunkest_turn"] = [1 if i % 5 == 0 else 2 if i % 5 in {1, 2, 3} else 3 for i in range(40)]
    players["expected_min"] = 24.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })
    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    candidates = solution.players.loc[
        solution.players["slot"].eq("Bench") & solution.players["dunkest_turn"].lt(3)
    ]
    player = candidates.iloc[0]
    name = str(player["player_name"])
    own_turn = int(player["dunkest_turn"])
    later_turn = next(turn for turn in (1, 2, 3) if turn > own_turn)
    lineup = solution.meta["turn_lineups"][str(later_turn)]
    replacement = next(
        name for name, slot in lineup["slots"].items()
        if slot == "Starter" and name != solution.captain
    )
    lineup["slots"][name] = "Starter"
    lineup["slots"][replacement] = "Bench"
    role_counts = pd.Series({
        player_name: lineup["roles"][player_name]
        for player_name, slot in lineup["slots"].items()
        if slot in {"Starter", "Captain"}
    }).value_counts().to_dict()
    lineup["module"] = f"{role_counts.get('G', 0)}-{role_counts.get('F', 0)}-{role_counts.get('C', 0)}"

    with pytest.raises(ValueError, match="promoted after playing in Dunkest turn"):
        validate_solution(solution, coaches, settings)


def test_dynamic_lineup_validator_rejects_captain_change_to_player_who_played():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.target_dunkest_turn = None
    players = _sample_players(40)
    players["dunkest_turn"] = [1 if i % 5 == 0 else 2 if i % 5 in {1, 2, 3} else 3 for i in range(40)]
    players["expected_min"] = 24.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })
    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
    final_lineup = solution.meta["turn_lineups"]["3"]
    already_played_starter = next(
        name for name, slot in final_lineup["slots"].items()
        if slot == "Starter" and solution.players.set_index("player_name").loc[name, "dunkest_turn"] < 3
    )
    final_lineup["slots"][already_played_starter] = "Captain"

    with pytest.raises(ValueError, match="captain assignment is inconsistent"):
        validate_solution(solution, coaches, settings)


def test_dynamic_optimizer_returns_three_independently_valid_lineups():
    settings = Settings.from_yaml()
    settings.budget = 95.0
    settings.target_dunkest_turn = None
    players = _sample_players(60)
    players["dunkest_turn"] = [1 if i % 5 == 0 else 2 if i % 5 in {1, 2, 3} else 3 for i in range(60)]
    players["expected_min"] = 24.0
    coaches = pd.DataFrame({
        "coach": ["HC0", "HC1", "HC2", "HC3"],
        "team": ["T0", "T1", "T2", "T3"],
        "coach_cr": [7.0, 8.0, 9.0, 10.0],
        "expected_coach_pdk": [5.0, 6.0, 7.0, 8.0],
    })

    solutions = optimize_top_k_lineups(players, coaches, settings, k=3)

    assert len(solutions) == 3
    assert len({solution.captain for solution in solutions}) == 3
    assert len({solution.coach for solution in solutions}) == 3
    assert [solution.expected_team_pdk for solution in solutions] == sorted(
        (solution.expected_team_pdk for solution in solutions), reverse=True
    )
    rosters = [set(solution.players["player_name"]) for solution in solutions]
    for solution in solutions:
        assert solution.meta["validation"]["valid"] is True
        assert len(solution.players) == 10
        assert solution.budget_used <= settings.budget
        assert solution.players["role"].value_counts().to_dict() == {"G": 4, "F": 4, "C": 2}
        coach_team = coaches.set_index("coach").loc[solution.coach, "team"]
        assert solution.players.groupby("team").size().get(coach_team, 0) + 1 <= 3
        assert solution.meta["dynamic_turn_mode"] is True
        for turn, lineup in solution.meta["turn_lineups"].items():
            slots = pd.Series(lineup["slots"], dtype=str)
            assert int(slots.isin({"Starter", "Captain"}).sum()) == 5
            assert int(slots.eq("Sixth Man").sum()) == 1
            assert int(slots.eq("Bench").sum()) == 4
            expected_captains = 1 if turn in solution.meta["captain_schedule"] else 0
            assert int(slots.eq("Captain").sum()) == expected_captains
            if turn in solution.meta["captain_schedule"]:
                assert lineup["slots"][solution.meta["captain_schedule"][turn]] == "Captain"
    for rank, solution in enumerate(solutions):
        expected_overlaps = {
            str(previous_rank + 1): len(rosters[rank] & rosters[previous_rank])
            for previous_rank in range(rank)
        }
        assert solution.meta["overlap_with_prior_ranks"] == expected_overlaps
        assert solution.overlap_with_previous == (
            expected_overlaps.get(str(rank)) if rank > 0 else None
        )


def test_injury_doubt_players_remain_candidates_using_availability_adjusted_score():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    # This is the expected score after P(play) has already been applied by
    # predict_players; the optimizer must not apply the probability twice.
    players.loc[0, "expected_pdk"] = 30.0
    players.loc[0, "p10"] = 0.0
    players.loc[0, "p50"] = 0.0
    players.loc[0, "p90"] = 30.0
    players.loc[0, "p_play"] = 0.5
    players.loc[0, "status"] = "Questionable (50%)"
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert "P0" in set(solution.players["player_name"])


def test_zero_minute_player_cannot_be_assigned_a_playing_slot():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    players["expected_min"] = 24.0
    players.loc[0, "expected_min"] = 0.0
    players.loc[0, "expected_pdk"] = 100.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
    zero_minute_slot = solution.players.set_index("player_name").loc["P0", "slot"]

    assert zero_minute_slot == "Bench"


def test_missing_minutes_do_not_become_starter_minutes():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    players["expected_min"] = 24.0
    players.loc[0, "expected_min"] = float("nan")
    players.loc[0, "expected_pdk"] = 100.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
    missing_minute_slot = solution.players.set_index("player_name").loc["P0", "slot"]

    assert missing_minute_slot == "Bench"


def test_optimizer_solution_includes_solver_diagnostics():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(_sample_players(), coaches, settings, k=1)[0]
    diagnostics = solution.meta["solver"]

    assert diagnostics["solver"] == "CBC"
    assert diagnostics["status"] == "Optimal"
    assert diagnostics["solve_time_seconds"] >= 0.0
    assert diagnostics["time_limit_seconds"] == settings.optimizer_time_limit_seconds


def test_tied_optimizer_solution_is_independent_of_input_row_order():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players()
    players["expected_pdk"] = 20.0
    coaches = pd.DataFrame({
        "coach": ["Coach B", "Coach A"], "team": ["T8", "T9"],
        "coach_cr": [7.0, 7.0], "expected_coach_pdk": [5.0, 5.0],
    })

    forward = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
    reversed_input = optimize_top_k_lineups(
        players.iloc[::-1], coaches.iloc[::-1], settings, k=1
    )[0]

    assert set(forward.players["player_name"]) == set(reversed_input.players["player_name"])
    assert forward.captain == reversed_input.captain
    assert forward.coach == reversed_input.coach


def test_missing_coaches_cannot_create_fake_dunkest_lineups():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    with pytest.raises(ValueError, match="Dati coach assenti"):
        optimize_top_k_lineups(_sample_players(), pd.DataFrame(), settings, k=1)


def test_non_finite_player_projection_fails_with_player_context():
    settings = Settings.from_yaml()
    players = _sample_players()
    players.loc[3, "expected_pdk"] = float("nan")
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    with pytest.raises(ValueError, match="Non-finite player optimizer field expected_pdk.*P3"):
        optimize_top_k_lineups(players, coaches, settings, k=1)


def test_non_finite_coach_projection_fails_before_solver():
    settings = Settings.from_yaml()
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [float("inf")],
    })

    with pytest.raises(ValueError, match="Non-finite coach optimizer field expected_coach_pdk.*HC"):
        optimize_top_k_lineups(_sample_players(), coaches, settings, k=1)


def test_unknown_roster_role_is_rejected_instead_of_becoming_unselectable():
    settings = Settings.from_yaml()
    players = _sample_players()
    players.loc[0, "role"] = "P"
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    with pytest.raises(ValueError, match="Unsupported player role.*P"):
        optimize_top_k_lineups(players, coaches, settings, k=1)


def test_duplicate_normalized_player_identity_is_rejected():
    settings = Settings.from_yaml()
    players = _sample_players()
    players.loc[1, "player_name"] = "P0 Jr."
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    with pytest.raises(ValueError, match="duplicate normalized player names"):
        optimize_top_k_lineups(players, coaches, settings, k=1)


def test_optimizer_normalizes_role_and_team_codes_before_constraints():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players()
    players["role"] = players["role"].str.lower()
    players["team"] = players["team"].str.lower()
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["t9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert set(solution.players["role"]) == {"G", "F", "C"}
    assert all(team == team.upper() for team in solution.players["team"])
    assert solution.meta["validation"]["valid"] is True


def test_independent_solution_validator_rejects_modified_score():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players()
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })
    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
    solution.expected_team_pdk += 1.0

    with pytest.raises(ValueError, match="reported team score does not match"):
        validate_solution(solution, coaches, settings)


def test_top_k_is_ranked_by_configured_optimizer_objective():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.optimizer_objective = "risk_adjusted"
    settings.risk_lambda = 0.5
    players = _sample_players()
    players["p10"] = players["expected_pdk"] - 2
    players["p50"] = players["expected_pdk"]
    players["p90"] = players["expected_pdk"] + 2
    players.loc[0, "p10"] = 0
    players.loc[0, "p90"] = 60
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0], "p10_coach_pdk": [5.0],
        "p50_coach_pdk": [5.0], "p90_coach_pdk": [5.0],
    })

    solutions = optimize_top_k_lineups(players, coaches, settings, k=3)

    objective_values = [solution.meta["solver_objective_value"] for solution in solutions]
    assert objective_values == sorted(objective_values, reverse=True)


def test_capital_gain_uses_positive_slate_shadow_value_even_with_slack_budget():
    settings = Settings.from_yaml()
    settings.budget = 200.0  # Slack budget: an extra CR has no current optimizer value.
    players = _sample_players(40)
    players["expected_min"] = 24.0
    players["expected_plusvalenza"] = 0.5
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert solution.meta["capital_gain_shadow_price"] > 0.0
    assert solution.meta["capital_gain_shadow_price_method"] in {
        "conservative_slate_productivity_proxy", "conservative_slate_productivity_floor"
    }
    assert solution.meta["expected_budget_gain"] == pytest.approx(5.0)
    assert solution.meta["future_budget_value_pdk"] > 0.0
    assert solution.meta["validation"]["valid"] is True


def test_optimizer_accounts_capital_gain_for_all_roster_slots():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    players["expected_min"] = 24.0
    players["expected_plusvalenza"] = 0.2
    players.loc[0, "expected_plusvalenza"] = 1.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })
    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
    selected = solution.players
    assert solution.meta["expected_budget_gain"] == pytest.approx(
        selected["expected_plusvalenza"].sum()
    )
    assert "optimizer_plusvalenza_priority" not in selected


def test_plusvalenza_changes_roster_selection_even_when_budget_is_slack():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    players = _sample_players(40)
    players["cr"] = 8.0
    players["expected_pdk"] = 20.0
    players["p10"] = 20.0
    players["p50"] = 20.0
    players["p90"] = 20.0
    players["expected_plusvalenza"] = 0.0
    players.loc[0, "expected_plusvalenza"] = 1.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert "P0" in set(solution.players["player_name"])
    assert solution.meta["capital_gain_shadow_price"] > 0.0
    assert solution.meta["future_budget_value_pdk"] == pytest.approx(
        solution.meta["expected_budget_gain"] * solution.meta["capital_gain_shadow_price"]
    )
    assert solution.meta["validation"]["valid"] is True


def test_tight_budget_gets_positive_empirical_credit_shadow_value():
    settings = Settings.from_yaml()
    settings.budget = 95.0
    players = _sample_players(40)
    players["expected_min"] = 24.0
    players["expected_plusvalenza"] = 0.5
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [7.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert solution.meta["capital_gain_shadow_price"] > 0.0
    assert solution.meta["future_budget_value_pdk"] > 0.0
    assert solution.meta["solver_objective_value"] == pytest.approx(
        solution.expected_team_pdk + solution.meta["future_budget_value_pdk"]
    )


def test_optimizer_accepts_exact_budget_solution():
    settings = Settings.from_yaml()
    settings.budget = 95.0
    players = _sample_players()
    players["cr"] = 8.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [15.0],
        "expected_coach_pdk": [5.0],
    })

    solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert solution.budget_used == pytest.approx(settings.budget)
    assert solution.meta["validation"]["valid"] is True


def test_optimizer_reports_infeasible_when_budget_is_one_credit_too_low():
    settings = Settings.from_yaml()
    settings.budget = 94.0
    players = _sample_players()
    players["cr"] = 8.0
    coaches = pd.DataFrame({
        "coach": ["HC"], "team": ["T9"], "coach_cr": [15.0],
        "expected_coach_pdk": [5.0],
    })

    with pytest.raises(ValueError, match="No feasible Dunkest lineup"):
        optimize_top_k_lineups(players, coaches, settings, k=1)


def test_optimizer_trades_down_at_coach_to_fund_a_better_joint_lineup():
    settings = Settings.from_yaml()
    settings.budget = 95.0
    players = _sample_players(40)
    players["cr"] = 8.0
    players["expected_pdk"] = 10.0
    players["p10"] = 8.0
    players["p50"] = 10.0
    players["p90"] = 12.0
    players["expected_min"] = 24.0
    premium = players.groupby("role", sort=False).head(1).index
    players.loc[premium, "cr"] = 18.0
    players.loc[premium, "expected_pdk"] = 20.0
    players.loc[premium, "p50"] = 20.0
    coaches = pd.DataFrame([
        {"coach": "Expensive coach", "team": "COACH_A", "coach_cr": 15.0,
         "expected_coach_pdk": 20.0, "opponent": "X"},
        {"coach": "Value coach", "team": "COACH_B", "coach_cr": 5.0,
         "expected_coach_pdk": 12.0, "opponent": "Y"},
    ])

    lineup = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert lineup.coach == "Value coach"
    assert set(players.loc[premium, "player_name"]) & set(lineup.players["player_name"])
    assert lineup.budget_used <= settings.budget


def test_neutral_coach_mode_prefers_cheaper_coach():
    settings = Settings.from_yaml()
    settings.budget = 200.0
    settings.use_coach_model = False
    coaches = pd.DataFrame([
        {"coach": "Expensive", "team": "COACH_A", "coach_cr": 14.0,
         "expected_coach_pdk": 0.0, "opponent": "X"},
        {"coach": "Affordable", "team": "COACH_B", "coach_cr": 5.0,
         "expected_coach_pdk": 0.0, "opponent": "Y"},
    ])

    lineup = optimize_top_k_lineups(_sample_players(40), coaches, settings, k=1)[0]

    assert lineup.coach == "Affordable"


def test_risk_adjusted_objective_accounts_for_coach_score_uncertainty():
    settings = Settings.from_yaml()
    settings.budget = 95.0
    settings.optimizer_objective = "risk_adjusted"
    settings.risk_lambda = 0.2
    players = _sample_players(40)
    players["cr"] = 8.0
    players["expected_pdk"] = 10.0
    players["p10"] = 9.0
    players["p50"] = 10.0
    players["p90"] = 11.0
    players["expected_min"] = 24.0
    coaches = pd.DataFrame([
        {"coach": "High variance", "team": "COACH_A", "coach_cr": 10.0,
         "expected_coach_pdk": 30.0, "p10_coach_pdk": -20.0,
         "p50_coach_pdk": 30.0, "p90_coach_pdk": 60.0, "opponent": "X"},
        {"coach": "Stable matchup", "team": "COACH_B", "coach_cr": 10.0,
         "expected_coach_pdk": 20.0, "p10_coach_pdk": 19.0,
         "p50_coach_pdk": 20.0, "p90_coach_pdk": 21.0, "opponent": "Y"},
    ])

    lineup = optimize_top_k_lineups(players, coaches, settings, k=1)[0]

    assert lineup.coach == "Stable matchup"
    assert lineup.expected_coach_pdk == 20.0  # reported value stays the unpenalized expectation
    assert lineup.p90_team - lineup.p50_team >= 1.0
