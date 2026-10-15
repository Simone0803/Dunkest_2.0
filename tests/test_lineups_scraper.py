import csv
import json

from dunkest.data.dunkest.lineups_browser import (
    _lineups_browser_profile_dir,
    _click_fixture,
    _advance_fixture_scroll,
    _apply_lineup_annotations,
    _filter_plausible_unavailable_annotations,
    _match_unavailable_to_market,
    merge_turn_market_snapshots,
    _all_fixtures_from_accessibility_nodes,
    _annotations_from_ocr_tsv,
    _collect_lineup_annotations,
    _collect_lineup_annotations_state,
    _cap_fixture_lineup_annotations,
    _fixtures_from_accessibility_nodes,
    _fixture_labels_from_batches,
    _fixture_turn_map_from_batches,
    _fixture_observation,
    _retain_previous_verified_fixture_eligibility,
    _fixture_present_in_market_response,
    _latest_fixture_market_matches,
    _deduplicate_market_rows,
    _fixture_lineup_coverage,
    _fixture_lineup_coverage_ok,
    _fixture_required_lineup_teams,
    _fixture_team_eligibility,
    _resolve_fixture_team_status,
    _visible_word_luminance,
    _fixture_status_from_luminance,
    _fixture_card_pixel_status,
    _normalize_ocr_team_code,
    _flatten_market,
    _parse_lineup_label,
    _teams_in_fixtures,
)


def test_lineups_browser_profile_is_persistent_and_outside_project_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DUNKEST_LINEUPS_PROFILE", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert _lineups_browser_profile_dir() == tmp_path / ".dunkest-optimizer" / "lineups-browser-profile"


def test_lineups_browser_profile_can_be_configured(monkeypatch, tmp_path):
    configured = tmp_path / "private-browser-profile"
    monkeypatch.setenv("DUNKEST_LINEUPS_PROFILE", str(configured))

    assert _lineups_browser_profile_dir() == configured


def test_click_fixture_scrolls_virtualized_card_into_view_before_activation():
    events = []

    class Candidate:
        def get_attribute(self, name, timeout=None):
            return None

        def inner_text(self, timeout=None):
            return "21/10 PHI @ NYK"

        def scroll_into_view_if_needed(self, timeout=None):
            events.append("scroll")

        def click(self, **kwargs):
            assert kwargs.get("force", False) is False
            events.append("click")

    class Candidates:
        def count(self):
            return 1

        def all(self):
            return [Candidate()]

    class Page:
        def get_by_role(self, role, name=None):
            assert role == "button"
            return Candidates()

        def wait_for_timeout(self, milliseconds):
            events.append("wait")

    assert _click_fixture(Page(), "21/10 PHI @ NYK")
    assert events == ["scroll", "click", "wait"]


def test_advance_fixture_scroll_recognizes_matchup_labels_with_regex_boundaries():
    class Page:
        def evaluate(self, script):
            assert r"const game = /\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b/i" in script
            return True

        def wait_for_timeout(self, milliseconds):
            pass

    _advance_fixture_scroll(Page())


def test_fixtures_are_scoped_to_the_requested_dunkest_turn():
    nodes = [
        {"label": "TURNO 1", "y": 10},
        {"label": "20/10 BOS @ DET", "y": 20},
        {"label": "21/10 PHI @ NYK", "y": 30},
        {"label": "TURNO 2", "y": 40},
        {"label": "22/10 ATL @ ORL", "y": 50},
    ]

    assert _fixtures_from_accessibility_nodes(nodes, 1) == ["20/10 BOS @ DET", "21/10 PHI @ NYK"]
    assert _fixtures_from_accessibility_nodes(nodes, 2) == ["22/10 ATL @ ORL"]
    assert _all_fixtures_from_accessibility_nodes(nodes) == [
        "20/10 BOS @ DET", "21/10 PHI @ NYK", "22/10 ATL @ ORL"
    ]


def test_lazy_fixture_batches_keep_round_heading_context_and_merge_all_matches():
    batches = [
        [{"label": "TURNO 1", "y": 5}, {"label": "20/10 BOS @ DET", "y": 15}],
        [{"label": "21/10 PHI @ NYK", "y": 10}, {"label": "22/10 OKC @ SAS", "y": 20}],
        [{"label": "TURNO 2", "y": 5}, {"label": "23/10 ATL @ ORL", "y": 15}],
    ]

    all_fixtures, round_one = _fixture_labels_from_batches(batches, 1)

    assert len(all_fixtures) == 4
    assert round_one == ["20/10 BOS @ DET", "21/10 PHI @ NYK", "22/10 OKC @ SAS"]
    assert _fixture_turn_map_from_batches(batches) == {
        "20/10 BOS @ DET": 1,
        "21/10 PHI @ NYK": 1,
        "22/10 OKC @ SAS": 1,
        "23/10 ATL @ ORL": 2,
    }


def test_full_gameweek_mode_targets_fixtures_from_every_turn_in_one_scan():
    batches = [
        [{"label": "TURNO 1", "y": 5}, {"label": "20/10 BOS @ DET", "y": 15}],
        [{"label": "TURNO 2", "y": 5}, {"label": "21/10 PHI @ NYK", "y": 15}],
        [{"label": "TURNO 3", "y": 5}, {"label": "22/10 OKC @ SAS", "y": 15}],
    ]

    all_fixtures, target_fixtures = _fixture_labels_from_batches(batches, None)

    assert target_fixtures == all_fixtures == [
        "20/10 BOS @ DET", "21/10 PHI @ NYK", "22/10 OKC @ SAS"
    ]


def test_starter_cap_distinguishes_same_surname_by_role_and_cr():
    annotations = [
        {"team": "BOS", "surname": name, "role": role, "cr": cr, "lineup_group": "QUINTETTO"}
        for name, role, cr in [
            ("tatum", "A", 18), ("brown", "A", 15), ("white", "G", 12),
            ("holiday", "G", 10), ("williams", "A", 9), ("williams", "G", 4.5),
        ]
    ]

    capped = _cap_fixture_lineup_annotations(annotations, {"BOS", "DET"})

    assert sum(row["lineup_group"] == "QUINTETTO" for row in capped if row["team"] == "BOS") == 5
    assert any(row["surname"] == "williams" and row["role"] == "G" and row["lineup_group"] == "PANCHINA" for row in capped)


def test_required_teams_come_from_the_displayed_schedule_not_every_nba_franchise():
    assert _teams_in_fixtures(["20/10 BOS @ DET", "21/10 PHI @ NYK"]) == {
        "BOS", "DET", "PHI", "NYK"
    }


def test_fixture_observations_preserve_lineups_turn_and_date():
    observation = _fixture_observation(
        "TURNO 1 20/10 BOS VS DET", 1, "2026-10-10T08:00:00+00:00"
    )

    assert observation["team_a"] == "BOS"
    assert observation["team_b"] == "DET"
    assert (observation["display_day"], observation["display_month"]) == ("20", "10")
    assert observation["dunkest_turn"] == 1


def test_lineups_response_extracts_full_names_current_cr_and_coaches():
    response = {
        "data": {
            "home_team": {
                "abbreviation": "BOS",
                "lineups": [
                    {"first_name": "Jayson", "last_name": "Tatum", "position": "Forward", "quotation": 18},
                ],
                "coach": {"first_name": "Joe", "last_name": "Mazzulla", "quotation": 8},
            },
            "away_team": {
                "abbreviation": "DET",
                "lineups": [
                    {"first_name": "Cade", "last_name": "Cunningham", "position": "Guard", "quotation": 21},
                ],
                "coach": {"first_name": "J.B.", "last_name": "Bickerstaff", "quotation": 9.5},
            },
        }
    }

    rows = _flatten_market(response)

    assert {
        (row["player_name"], row["cr"], row["team"], row["role"])
        for row in rows
    } == {
        ("Jayson Tatum", 18.0, "BOS", "A"),
        ("Joe Mazzulla", 8.0, "BOS", "HC"),
        ("Cade Cunningham", 21.0, "DET", "G"),
        ("J.B. Bickerstaff", 9.5, "DET", "HC"),
    }


def test_lineups_entity_id_and_slug_are_preserved_for_identity_audit():
    response = {
        "data": {
            "home_team": {
                "abbreviation": "BOS",
                "lineups": [{
                    "id": 434, "slug": "jayson-tatum", "first_name": "Jayson",
                    "last_name": "Tatum", "position": "Forward", "quotation": 18,
                }],
            },
            "away_team": {
                "abbreviation": "DET",
                "lineups": [{
                    "player_id": "9999", "first_name": "Test", "last_name": "Rookie",
                    "position": "Guard", "quotation": 4.5,
                }],
            },
        }
    }

    rows = _flatten_market(response)
    tatum = next(row for row in rows if row["player_name"] == "Jayson Tatum")
    rookie = next(row for row in rows if row["player_name"] == "Test Rookie")
    assert tatum["lineups_entity_id"] == "434"
    assert tatum["lineups_entity_slug"] == "jayson-tatum"
    assert rookie["lineups_entity_id"] == "9999"
    assert "lineups_entity_slug" not in rookie


def test_non_numeric_lineups_entity_id_is_not_preserved():
    response = {"team": {"abbreviation": "BOS", "lineups": [{
        "id": "player-abc", "first_name": "Jayson", "last_name": "Tatum",
        "position": "Forward", "quotation": 18,
    }]}}
    row = _flatten_market(response)[0]
    assert "lineups_entity_id" not in row


def test_already_selected_fixture_is_verified_from_its_api_market():
    response = {"data": {"home_team": {
        "abbreviation": "BOS", "lineups": [
            {"first_name": "Jayson", "last_name": "Tatum", "position": "Forward", "quotation": 18}
        ]
    }, "away_team": {
        "abbreviation": "DET", "lineups": [
            {"first_name": "Cade", "last_name": "Cunningham", "position": "Guard", "quotation": 21}
        ]
    }}}

    assert _fixture_present_in_market_response([("url", 200, response)], "TURNO 1 20/10 BOS @ DET")
    assert not _fixture_present_in_market_response([("url", 200, response)], "21/10 PHI @ NYK")



def test_repeated_market_responses_are_deduplicated_before_lineup_annotation():
    market = []
    annotations = []
    for team, prefix, surnames in (
        ("BOS", "Boston", ("Tatum", "White", "Brown", "Holiday", "Pritchard")),
        ("DET", "Detroit", ("Cunningham", "Harris", "Duren", "Thompson", "Ivey")),
    ):
        for surname in surnames:
            row = {
                "player_name": f"{prefix} {surname}", "team": team,
                "role": "A", "cr": 8.0,
            }
            market.append(row)
            annotations.append(_parse_lineup_label(f"A {surname} 8cr", team, "QUINTETTO"))
        for surname in ("BenchOne", "BenchTwo", "BenchThree"):
            row = {
                "player_name": f"{prefix} {surname}", "team": team,
                "role": "A", "cr": 4.0,
            }
            market.append(row)
            annotations.append(_parse_lineup_label(f"A {surname} 4cr", team, "PANCHINA"))

    repeated_market = market + [row.copy() for row in market] + [row.copy() for row in market]
    unique_market = _deduplicate_market_rows(repeated_market)
    matched, unavailable = _apply_lineup_annotations(unique_market, annotations)

    assert len(unique_market) == 16
    assert (matched, unavailable) == (16, 0)
    assert sum(row.get("lineup_group") == "QUINTETTO" for row in unique_market) == 10
    assert sum(row.get("lineup_group") == "PANCHINA" for row in unique_market) == 6


def test_fixture_lineup_coverage_requires_five_market_matched_starters_per_side():
    market = []
    annotations = []
    for team, prefix in (("BOS", "Boston"), ("DET", "Detroit")):
        for index, surname in enumerate(("Tatum", "White", "Brown", "Holiday", "Pritchard")):
            name = f"{prefix} {surname}"
            market.append({"player_name": name, "team": team, "role": "G", "cr": 8.0})
            annotations.append({
                "team": team, "surname": surname.casefold(), "ui_name": surname.casefold(),
                "lineup_group": "QUINTETTO",
            })
        for index, surname in enumerate(("BenchA", "BenchB", "BenchC")):
            name = f"{prefix} {surname}"
            market.append({"player_name": name, "team": team, "role": "F", "cr": 4.0})
            annotations.append({
                "team": team, "surname": surname.casefold(), "ui_name": surname.casefold(),
                "lineup_group": "PANCHINA",
            })

    # The same full-league API roster may be repeated for every fixture response.
    market = market + [row.copy() for row in market]
    coverage = _fixture_lineup_coverage(annotations, "20/10 BOS @ DET", market)

    assert coverage == {
        "BOS": {"players": 8, "starters": 5},
        "DET": {"players": 8, "starters": 5},
    }
    assert _fixture_lineup_coverage_ok(coverage)


def test_fixture_lineup_coverage_resolves_reversed_visual_team_columns():
    market = []
    annotations = []
    for team, prefix, surnames in (
        ("BOS", "Boston", ("Tatum", "White", "Brown", "Holiday", "Pritchard")),
        ("DET", "Detroit", ("Cunningham", "Harris", "Duren", "Thompson", "Ivey")),
    ):
        for surname in (*surnames, "BenchOne", "BenchTwo", "BenchThree"):
            market.append({"player_name": f"{prefix} {surname}", "team": team, "role": "G", "cr": 8.0})
            # Deliberately assign each label to the opposite visual column.
            annotations.append({
                "team": "DET" if team == "BOS" else "BOS", "surname": surname.casefold(),
                "ui_name": surname.casefold(),
                "lineup_group": "QUINTETTO" if surname in surnames else "PANCHINA",
            })

    coverage = _fixture_lineup_coverage(annotations, "20/10 BOS @ DET", market)

    assert coverage["BOS"]["starters"] == 5
    assert coverage["DET"]["starters"] == 5
    assert _fixture_lineup_coverage_ok(coverage)


def test_fixture_lineup_coverage_requires_only_eligible_side_when_opponent_is_disabled():
    coverage = {
        "CLE": {"players": 15, "starters": 5},
        "PHI": {"players": 0, "starters": 0},
    }
    eligibility = {"23/10|CLE|PHI": {"CLE": True, "PHI": False}}

    required = _fixture_required_lineup_teams("TURNO 3 23/10 CLE @ PHI", eligibility)

    assert required == {"CLE"}
    assert _fixture_lineup_coverage_ok(coverage, required)
    assert not _fixture_lineup_coverage_ok(coverage)


def test_fixture_lineup_coverage_uses_displayed_cr_to_disambiguate_same_team_surnames():
    market = []
    annotations = []
    teams = {
        "OKC": ("Gilgeous-Alexander", "Caruso", "Wallace", "Williams", "Holmgren"),
        "SAS": ("Fox", "Vassell", "Castle", "Champagnie", "Wembanyama"),
    }
    for team, surnames in teams.items():
        for surname in surnames:
            price = 15.0 if team == "OKC" and surname == "Williams" else 8.0
            market.append({"player_name": f"{team} {surname}", "team": team, "role": "A", "cr": price})
            annotations.append({
                "team": team, "surname": surname.casefold(), "ui_name": surname.casefold(),
                "role": "A", "cr": price, "lineup_group": "QUINTETTO",
            })
        for surname in ("BenchOne", "BenchTwo", "BenchThree"):
            market.append({"player_name": f"{team} {surname}", "team": team, "role": "G", "cr": 4.0})
            annotations.append({
                "team": team, "surname": surname.casefold(), "ui_name": surname.casefold(),
                "role": "G", "cr": 4.0, "lineup_group": "PANCHINA",
            })
    market.append({"player_name": "Jaylin Williams", "team": "OKC", "role": "A", "cr": 5.0})

    coverage = _fixture_lineup_coverage(annotations, "21/10 OKC @ SAS", market)

    assert coverage["OKC"]["starters"] == 5
    assert coverage["SAS"]["starters"] == 5
    assert _fixture_lineup_coverage_ok(coverage)


def test_fixture_lineup_coverage_rejects_stale_panel_players_assigned_to_wrong_teams():
    market = []
    stale_annotations = []
    team_names = {
        "BOS": ("Tatum", "White", "Brown", "Holiday", "Pritchard"),
        "DET": ("Cunningham", "Harris", "Duren", "Thompson", "Ivey"),
        "SAS": ("Vassell", "Fox", "Castle", "Wembanyama", "Champagnie"),
    }
    for team, prefix in (("BOS", "Boston"), ("DET", "Detroit"), ("SAS", "SanAntonio")):
        for index, surname in enumerate(team_names[team]):
            market.append({"player_name": f"{prefix} {surname}", "team": team, "role": "G", "cr": 8.0})
            if team == "SAS":
                stale_annotations.append({
                    "team": "BOS" if index < 3 else "DET", "surname": surname.casefold(),
                    "ui_name": surname.casefold(), "lineup_group": "QUINTETTO",
                })

    coverage = _fixture_lineup_coverage(stale_annotations, "20/10 BOS @ DET", market)

    assert coverage == {
        "BOS": {"players": 0, "starters": 0},
        "DET": {"players": 0, "starters": 0},
    }
    assert not _fixture_lineup_coverage_ok(coverage)


def test_latest_fixture_market_match_does_not_accept_an_old_response():
    bos = {"players": [{"name": "Player BOS", "team": "BOS", "position": "G", "cr": 5},
                       {"name": "Player DET", "team": "DET", "position": "F", "cr": 5}]}
    phi = {"players": [{"name": "Player PHI", "team": "PHI", "position": "G", "cr": 5},
                       {"name": "Player NYK", "team": "NYK", "position": "F", "cr": 5}]}
    responses = [("bos", 200, bos), ("phi", 200, phi)]

    assert _latest_fixture_market_matches(responses, "21/10 PHI @ NYK")
    assert not _latest_fixture_market_matches(responses, "20/10 BOS @ DET")
    assert _latest_fixture_market_matches(responses[:1], "20/10 BOS @ DET")
    assert not _latest_fixture_market_matches(responses[:1], "21/10 PHI @ NYK")


def test_lineups_accessibility_labels_carry_starter_bench_injury_and_coach_cr():
    rows = [
        {"player_name": "Stephen Curry", "cr": 15.0, "team": "GSW", "role": "G"},
        {"player_name": "Jimmy Butler", "cr": 12.0, "team": "GSW", "role": "A"},
        {"player_name": "Steve Kerr", "cr": 7.0, "team": "GSW", "role": "HC"},
    ]
    annotations = [
        _parse_lineup_label("G CURRY 15cr 0", "GSW", "QUINTETTO"),
        _parse_lineup_label("A BUTLER 0", "GSW", "INDISPONIBILI"),
        _parse_lineup_label("HC KERR 8cr 0", "GSW", "COACH"),
    ]

    count, unavailable = _apply_lineup_annotations(
        rows, [annotation for annotation in annotations if annotation], {"GSW": "Steve Kerr"}
    )

    assert count == 3
    assert unavailable == 1
    curry = next(row for row in rows if row["player_name"] == "Stephen Curry")
    butler = next(row for row in rows if row["player_name"] == "Jimmy Butler")
    coach = next(row for row in rows if row["role"] == "HC")
    assert curry["starter"] == "true"
    assert butler["status"] == "OUT"
    assert coach["cr"] == 8.0


def test_injury_annotation_discards_advertisements_and_fixture_captions():
    assert _parse_lineup_label("Advertisement", "DET", "INDISPONIBILI") is None
    assert _parse_lineup_label(
        "Philadelphia 76Ers 21/10 01:00 New York Knicks", "NYK", "INDISPONIBILI"
    ) is None
    assert _parse_lineup_label("quaintance *", "SAS", "INDISPONIBILI") is None


def test_scroll_merged_fixture_annotations_cap_starters_and_dedupe_scroll_duplicates():
    annotations = [
        {
            "team": "ATL", "role": "G", "surname": f"PLAYER{i}",
            "ui_name": f"Player {i}", "lineup_group": "QUINTETTO",
            "_fixture_teams": ("ATL", "ORL"),
        }
        for i in range(1, 10)
    ]
    annotations.extend([
        {
            "team": "ATL", "role": "G", "surname": "player1",
            "ui_name": "Player 1", "lineup_group": "PANCHINA",
            "_fixture_teams": ("ATL", "ORL"),
        },
        {
            "team": "ATL", "role": "G", "surname": "PLAYER9",
            "ui_name": "Player 9", "lineup_group": "QUINTETTO",
            "_fixture_teams": ("ATL", "ORL"),
        },
    ])

    result = _cap_fixture_lineup_annotations(annotations, {"ATL", "ORL"})
    starters = [item for item in result if item["team"] == "ATL" and item["lineup_group"] == "QUINTETTO"]
    benches = [item for item in result if item["team"] == "ATL" and item["lineup_group"] == "PANCHINA"]

    assert len(starters) == 5
    assert len(benches) == 4
    assert len({item["surname"] for item in result if item["team"] == "ATL"}) == len(
        [item for item in result if item["team"] == "ATL"]
    )


def test_lineup_annotation_fallback_is_limited_to_fixture_teams():
    rows = [
        {"player_name": "Tyus Jones", "cr": 5.0, "team": "ORL", "role": "G"},
        {"player_name": "Tyus Jones", "cr": 5.0, "team": "SAS", "role": "G"},
        {"player_name": "Malcolm Miller", "cr": 4.0, "team": "BOS", "role": "F"},
    ]
    reversed_column = _parse_lineup_label("G JONES 5cr", "ATL", "QUINTETTO")
    reversed_column["_fixture_teams"] = ("ATL", "ORL")
    unrelated = _parse_lineup_label("F MILLER 4cr", "ATL", "QUINTETTO")
    unrelated["_fixture_teams"] = ("ATL", "ORL")

    _apply_lineup_annotations(rows, [reversed_column, unrelated])

    orlando = next(row for row in rows if row["team"] == "ORL")
    san_antonio = next(row for row in rows if row["team"] == "SAS")
    boston = next(row for row in rows if row["team"] == "BOS")
    assert orlando["lineup_group"] == "QUINTETTO"
    assert san_antonio.get("lineup_group") is None
    assert boston.get("lineup_group") is None


def test_unavailable_player_is_resolved_even_if_visual_team_column_is_reversed():
    rows = [
        {"player_name": "Jimmy Butler", "cr": 12.0, "team": "GSW", "role": "A"},
        {"player_name": "LeBron James", "cr": 20.0, "team": "LAL", "role": "A"},
    ]
    unavailable = _parse_lineup_label("A BUTLER 8cr", "LAL", "INDISPONIBILI")

    matched, out_count = _apply_lineup_annotations(rows, [unavailable])

    assert (matched, out_count) == (1, 1)
    jimmy = next(row for row in rows if row["player_name"] == "Jimmy Butler")
    assert jimmy["team"] == "GSW"
    assert jimmy["status"] == "OUT"


def test_unavailable_plain_name_without_position_is_matched_by_unique_surname():
    rows = [{"player_name": "Jimmy Butler", "cr": 12.0, "team": "GSW", "role": "A"}]
    unavailable = _parse_lineup_label("Jimmy Butler", "GSW", "INDISPONIBILI")

    matched, out_count = _apply_lineup_annotations(rows, [unavailable])

    assert (matched, out_count) == (1, 1)
    assert rows[0]["status"] == "OUT"


def test_out_status_cannot_be_overwritten_by_a_later_fixture_lineup():
    rows = [{"player_name": "Jimmy Butler", "cr": 12.0, "team": "GSW", "role": "A"}]
    out = _parse_lineup_label("A BUTLER", "GSW", "INDISPONIBILI")
    later_starter = _parse_lineup_label("A BUTLER 12cr", "GSW", "QUINTETTO")

    _apply_lineup_annotations(rows, [out, later_starter])

    assert rows[0]["status"] == "OUT"
    assert rows[0]["lineup_group"] == "INDISPONIBILI"


def test_unavailable_ocr_suffixes_are_removed_before_matching():
    annotation = _parse_lineup_label("C HUKPORTI ©", "", "INDISPONIBILI")

    assert annotation["ui_name"] == "hukporti"
    assert annotation["surname"] == "hukporti"


def test_teamless_injury_annotation_resolves_only_a_unique_surname():
    unique_rows = [
        {"player_name": "Brandon Ingram", "cr": 12.0, "team": "LAC", "role": "A"},
        {"player_name": "Healthy Player", "cr": 5.0, "team": "BOS", "role": "G"},
    ]
    unique = _parse_lineup_label("INGRAM", "", "INDISPONIBILI")
    assert _match_unavailable_to_market(unique, unique_rows)["player_name"] == "Brandon Ingram"

    ambiguous_rows = unique_rows + [
        {"player_name": "Malcolm Miller", "cr": 4.0, "team": "NYK", "role": "F"},
        {"player_name": "Quincy Miller", "cr": 4.0, "team": "PHI", "role": "F"},
    ]
    ambiguous = _parse_lineup_label("MILLER", "", "INDISPONIBILI")
    assert _match_unavailable_to_market(ambiguous, ambiguous_rows) is None


def test_teamless_unavailable_match_deduplicates_repeated_fixture_api_rows():
    repeated_player = {"player_name": "Ariel Hukporti", "cr": 4.0, "team": "PHI", "role": "C"}
    rows = [
        {"player_name": "Jayson Tatum", "cr": 18.0, "team": "BOS", "role": "A"},
        repeated_player.copy(),
        repeated_player.copy(),
        repeated_player.copy(),
    ]
    unavailable = _parse_lineup_label("C HUKPORTI", "", "INDISPONIBILI")

    matched, out_count = _apply_lineup_annotations(rows, [unavailable])

    assert (matched, out_count) == (1, 1)
    # The matcher updates the last canonical row, which survives the scraper's
    # subsequent identity de-duplication.
    assert rows[-1]["status"] == "OUT"
    assert rows[-1]["lineup_group"] == "INDISPONIBILI"


def test_indisponibili_heading_with_count_is_recognized():
    class Page:
        def evaluate(self, _script):
            return {
                "width": 1000,
                "nodes": [
                    {"label": "QUINTETTO", "x": 250, "y": 10},
                    {"label": "HC KERR 8cr", "x": 250, "y": 40},
                    {"label": "INDISPONIBILI (1)", "x": 500, "y": 60},
                    {"label": "A BUTLER", "x": 250, "y": 80},
                    {"label": "Jimmy Butler", "x": 250, "y": 100},
                ],
            }

    annotations = _collect_lineup_annotations(Page(), "GSW @ LAL")

    assert [(x["surname"], x["lineup_group"]) for x in annotations] == [
        ("kerr", "QUINTETTO"), ("butler", "INDISPONIBILI")
    ]


def test_starter_bench_sections_are_scoped_to_their_team_column():
    class Page:
        def evaluate(self, _script):
            nodes = [
                {"label": "QUINTETTO", "x": 250, "y": 10},
                {"label": "QUINTETTO", "x": 750, "y": 12},
            ]
            nodes.extend(
                {"label": f"G HOME{i} 8cr", "x": 250, "y": 20 + i * 10}
                for i in range(1, 6)
            )
            nodes.extend(
                {"label": f"G AWAY{i} 8cr", "x": 750, "y": 22 + i * 10}
                for i in range(1, 6)
            )
            # The two columns can scroll/flow independently. A later heading
            # in the right column must not relabel the left team's bench row.
            nodes.extend([
                {"label": "PANCHINA", "x": 250, "y": 80},
                {"label": "QUINTETTO", "x": 750, "y": 85},
                {"label": "G HOME6 4cr", "x": 250, "y": 90},
                {"label": "G AWAY6 4cr", "x": 750, "y": 95},
            ])
            return {"width": 1000, "nodes": nodes}

    annotations = _collect_lineup_annotations(Page(), "PHI @ NYK")
    groups = {item["ui_name"]: item["lineup_group"] for item in annotations}

    assert groups["home6"] == "PANCHINA"
    assert groups["away6"] == "QUINTETTO"


def test_column_detection_uses_player_clusters_when_both_columns_left_of_viewport_midpoint():
    class Page:
        def evaluate(self, _script):
            nodes = [
                {"label": "QUINTETTO", "x": 350, "y": 10},
                {"label": "QUINTETTO", "x": 820, "y": 12},
            ]
            nodes.extend(
                {"label": f"G HOME{i} 8cr", "x": 350, "y": 20 + i * 10}
                for i in range(1, 6)
            )
            nodes.extend(
                {"label": f"G AWAY{i} 8cr", "x": 820, "y": 22 + i * 10}
                for i in range(1, 6)
            )
            nodes.extend([
                {"label": "PANCHINA", "x": 350, "y": 80},
                {"label": "QUINTETTO", "x": 820, "y": 85},
                {"label": "G HOME6 4cr", "x": 350, "y": 90},
                {"label": "G AWAY6 4cr", "x": 820, "y": 95},
            ])
            return {"width": 1680, "nodes": nodes}

    annotations = _collect_lineup_annotations(Page(), "PHI @ NYK")
    groups = {item["ui_name"]: item["lineup_group"] for item in annotations}

    assert groups["home6"] == "PANCHINA"
    assert groups["away6"] == "QUINTETTO"


def test_fixture_eligibility_fallback_preserves_a_previously_verified_30_team_slate():
    previous = []
    for i in range(15):
        a, b = f"T{i * 2:02d}", f"T{i * 2 + 1:02d}"
        previous.append({
            "fixture_label": f"{a} @ {b}", "team_a": a, "team_b": b,
            "display_day": str(20 + i), "display_month": "10",
            "dunkest_turn": 1 if i < 3 else 2, "team_a_eligible": True,
            "team_b_eligible": True, "observed_at_utc": "old",
        })
    current = [dict(row, observed_at_utc="new") for row in previous]
    current[-1]["team_b_eligible"] = False

    merged, conflicts = _retain_previous_verified_fixture_eligibility(current, previous)

    assert _eligible_teams_from_fixture_rows_for_test(merged) == {
        f"T{i:02d}" for i in range(30)
    }
    assert merged[-1]["team_b_eligible"] is True
    assert len(conflicts) == 1
    assert conflicts[0]["team"] == "T29"


def _eligible_teams_from_fixture_rows_for_test(rows):
    teams = set()
    for row in rows:
        if row["team_a_eligible"] is True:
            teams.add(row["team_a"])
        if row["team_b_eligible"] is True:
            teams.add(row["team_b"])
    return teams


def test_missing_bench_heading_caps_starters_at_five_per_fixture_column():
    class Page:
        def evaluate(self, _script):
            nodes = [{"label": "QUINTETTO", "x": 250, "y": 10}]
            nodes.extend(
                {"label": f"G PLAYER{i} 6cr", "x": 250, "y": 20 + i * 10}
                for i in range(1, 8)
            )
            return {"width": 1000, "nodes": nodes}

    annotations = _collect_lineup_annotations(Page(), "PHI @ NYK")
    groups = [item["lineup_group"] for item in annotations]

    assert groups.count("QUINTETTO") == 5
    assert groups.count("PANCHINA") == 2


def test_merge_turn_market_snapshots_keeps_only_roster_and_coach_annotations(tmp_path):
    fields = ["player_name", "cr", "team", "role", "lineup_group", "starter", "status", "dunkest_turn"]
    players = [
        ("Player One", "8.0", "BOS", "G"),
        ("Player Two", "7.0", "ATL", "G"),
        ("Player Three", "5.0", "NYK", "F"),
        ("Coach A", "7.5", "BOS", "HC"),
    ]
    groups = {
        1: {"Player One": ("QUINTETTO", "true", "AVAILABLE"),
            "Coach A": ("COACH", "", "")},
        2: {"Player One": ("INDISPONIBILI", "", "OUT"),
            "Player Two": ("QUINTETTO", "true", "AVAILABLE")},
        3: {"Player Three": ("PANCHINA", "false", "AVAILABLE")},
    }
    snapshots = []
    for turn in (1, 2, 3):
        path = tmp_path / f"market_turn{turn}.csv"
        snapshots.append(path)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for name, cr, team, role in players:
                group, starter, status = groups[turn].get(name, ("", "", ""))
                writer.writerow({
                    "player_name": name, "cr": cr, "team": team, "role": role,
                    "lineup_group": group, "starter": starter, "status": status,
                    "dunkest_turn": turn,
                })
        path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps({
            "dunkest_turn": turn,
            "fetched_at": f"2026-10-14T0{turn}:00:00+00:00",
            "fixtures_scanned": 16,
            "fixtures_total": 16,
            "fixtures_failed": [],
            "all_fixtures_covered": True,
            "target_fixtures_scanned": {1: 3, 2: 11, 3: 2}[turn],
            "target_fixtures_total": {1: 3, 2: 11, 3: 2}[turn],
            "target_fixtures_complete": True,
            "players": 3,
            "coaches": 1,
        }), encoding="utf-8")

    output = tmp_path / "current_lineups_market.csv"
    merge_turn_market_snapshots(snapshots, output)
    with output.open(newline="", encoding="utf-8") as stream:
        merged = {row["player_name"]: row for row in csv.DictReader(stream)}
    metadata = json.loads(output.with_suffix(output.suffix + ".meta.json").read_text(encoding="utf-8"))

    assert merged["Player One"]["status"] == ""
    assert merged["Player One"]["lineup_group"] == "QUINTETTO"
    assert merged["Player One"]["lineup_group_turn1"] == "QUINTETTO"
    assert merged["Player One"]["lineup_group_turn2"] == ""
    assert merged["Player One"]["status_turn2"] == ""
    assert merged["Player Two"]["lineup_group"] == "QUINTETTO"
    assert merged["Player Two"]["lineup_group_turn2"] == "QUINTETTO"
    assert merged["Player Three"]["lineup_group"] == "PANCHINA"
    assert merged["Player Three"]["lineup_group_turn3"] == "PANCHINA"
    assert merged["Coach A"]["lineup_group"] == "COACH"
    assert merged["Coach A"]["lineup_group_turn1"] == "COACH"
    assert {row["dunkest_turn"] for row in merged.values()} == {""}
    assert metadata["turns_captured"] == [1, 2, 3]
    assert metadata["target_fixtures_scanned"] == 16
    assert metadata["target_fixtures_total"] == 16
    assert metadata["target_fixtures_complete"] is True
    assert metadata["injury_statuses_included"] is False
    assert "INDISPONIBILI" not in metadata["lineup_group_counts"]


def test_roster_names_outside_explicit_unavailable_section_are_not_out():
    class Page:
        def evaluate(self, _script):
            return {
                "width": 1000,
                "nodes": [
                    {"label": "G RUPERT 4.5cr", "x": 250, "y": 20},
                    {"label": "G SHAMET 5cr", "x": 750, "y": 20},
                    {"label": "RUPERT", "x": 250, "y": 80},
                ],
            }

    annotations = _collect_lineup_annotations(Page(), "PHI @ NYK")

    assert annotations
    assert all(item["lineup_group"] != "INDISPONIBILI" for item in annotations)


def test_unavailable_section_context_survives_scroll_past_its_heading():
    class Page:
        def __init__(self, nodes):
            self.nodes = nodes

        def evaluate(self, _script):
            return {"width": 1000, "nodes": self.nodes}

    _, section_active = _collect_lineup_annotations_state(
        Page([{"label": "INDISPONIBILI", "x": 500, "y": 20}]), "NYK @ PHI"
    )
    annotations, _ = _collect_lineup_annotations_state(
        Page([{"label": "C HUKPORTI", "x": 250, "y": 20}]),
        "NYK @ PHI",
        unavailable_section_active=section_active,
    )

    assert len(annotations) == 1
    assert annotations[0]["ui_name"] == "hukporti"
    assert annotations[0]["lineup_group"] == "INDISPONIBILI"


def test_legend_text_after_unavailable_panel_ends_injury_context():
    class Page:
        def evaluate(self, _script):
            return {
                "width": 1000,
                "nodes": [
                    {"label": "INDISPONIBILI", "x": 500, "y": 10},
                    {"label": "A BUTLER", "x": 250, "y": 25},
                    {"label": "LEGENDA PUNTEGGI", "x": 500, "y": 35},
                    {"label": "quaintance", "x": 250, "y": 50},
                ],
            }

    annotations, section_active = _collect_lineup_annotations_state(Page(), "NYK @ PHI")

    assert [(item["surname"], item["lineup_group"]) for item in annotations] == [
        ("butler", "INDISPONIBILI")
    ]
    assert not section_active


def test_unavailable_panel_ignores_accessibility_and_advertising_copy():
    for label in (
        "learn more",
        "path to success",
        "nu samenstellen >",
        "ijzersterke",
        "hapert samen!",
        "stel nu jouw",
        "bekijk je premie",
        "hire an expert",
    ):
        assert _parse_lineup_label(label, "", "INDISPONIBILI") is None

    # Actual surnames remain parseable; ambiguity is resolved later against
    # the team-specific market rather than by broad text suppression.
    assert _parse_lineup_label("Sharpe", "BKN", "INDISPONIBILI")["surname"] == "sharpe"


def test_unavailable_annotations_filter_unscoped_ad_copy_using_market_surnames():
    rows = [
        {"player_name": "Day'ron Sharpe", "team": "BKN", "role": "C"},
        {"player_name": "Jordan Miller", "team": "LAC", "role": "G"},
        {"player_name": "Brandon Ingram", "team": "LAC", "role": "A"},
        {"player_name": "Cameron Johnson", "team": "BKN", "role": "F"},
    ]
    def annotation(label, team=""):
        return {
            "ui_name": label,
            "surname": label.casefold().split()[-1],
            "team": team,
            "role": "ANY",
            "lineup_group": "INDISPONIBILI",
        }

    annotations = [
        annotation("Sharpe"), annotation("Miller"), annotation("Ingram"),
        annotation("Johnson"), annotation("Mooier."), annotation("met Karwei"),
        annotation("Amsterdam"), annotation("Hotels"), annotation("Hire an expert"),
        annotation("Unknown Player", team="LAC"),
    ]
    filtered = _filter_plausible_unavailable_annotations(annotations, rows)
    assert [item["ui_name"] for item in filtered] == [
        "Sharpe", "Miller", "Ingram", "Johnson", "Unknown Player"
    ]


def test_legend_text_after_unavailable_panel_is_not_a_player():
    assert _parse_lineup_label("LEGENDA PUNTEGGI", "NYK", "INDISPONIBILI") is None


def test_ocr_fallback_reads_only_names_between_unavailable_heading_and_legend():
    def word(line, word, left, top):
        values = ["5", "1", "1", "1", str(line), "1", str(left), str(top), "30", "20", "95", word]
        return "\t".join(values)

    tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    tsv += "1\t1\t0\t0\t0\t0\t0\t0\t2456\t1514\t-1\t\n"
    tsv += "\n".join([
        word(1, "RUPERT", 50, 20),
        word(2, "INDISPONIBILI", 900, 100),
        word(3, "C", 900, 150),
        word(3, "HUKPORTI", 930, 150),
        word(3, "Leaders", 105, 150),
        word(4, "LEGENDA", 900, 200),
        word(4, "PUNTEGGI", 980, 200),
    ])

    annotations, panel_seen = _annotations_from_ocr_tsv(tsv)

    assert panel_seen
    assert len(annotations) == 1
    assert annotations[0]["surname"] == "hukporti"
    assert annotations[0]["lineup_group"] == "INDISPONIBILI"


def test_fixture_team_eligibility_uses_visible_css_color_and_opacity():
    assert _fixture_team_eligibility({"color": "rgb(0, 0, 0)", "opacity": 1.0}) is True
    assert _fixture_team_eligibility({"color": "rgb(160, 160, 160)", "opacity": 1.0}) is False
    assert _fixture_team_eligibility({"color": "rgb(0, 0, 0)", "opacity": 0.4}) is None
    assert _fixture_team_eligibility({"color": "rgba(0, 0, 0, 0.2)", "opacity": 1.0}) is None


def test_fixture_status_resolution_prefers_confident_dom_color():
    assert _resolve_fixture_team_status(
        "BOS",
        {"BOS": {"color": "rgb(0, 0, 0)", "opacity": 1.0}},
        {"BOS": False},
    ) is True
    assert _resolve_fixture_team_status(
        "DET",
        {"DET": {"color": "rgb(155, 155, 155)", "opacity": 1.0}},
        {"DET": True},
    ) is False


def test_fixture_status_resolution_uses_screenshot_only_when_dom_color_is_unknown():
    assert _resolve_fixture_team_status(
        "BOS",
        {"BOS": {"color": "rgba(0, 0, 0, 0.2)", "opacity": 1.0}},
        {"BOS": True},
    ) is True
    assert _resolve_fixture_team_status("BOS", {}, {}) is None


def test_ocr_ink_luminance_resists_antialiasing_gray_pixel_majority():
    # OCR's crop has a minority of black glyph-core pixels, gray edge pixels,
    # and a white background. A median would report gray (ineligible); the
    # lower-tail estimator recovers the dark glyph core.
    width, height = 14, 8
    pixels = bytearray([255, 255, 255] * width * height)
    # Populate only the inner word box; surrounding white pixels provide the
    # local background ring used to detect selected dark tiles.
    box_pixels = []
    for y in range(2, 6):
        for x in range(2, 12):
            box_pixels.append((y * width + x) * 3)
    for index in range(6):
        pixels[box_pixels[index]:box_pixels[index] + 3] = bytes([0, 0, 0])
    for index in range(6, 20):
        pixels[box_pixels[index]:box_pixels[index] + 3] = bytes([180, 180, 180])

    luminance = _visible_word_luminance((width, height, pixels), (2, 2, 12, 6))

    assert luminance is not None
    assert luminance <= 80


def test_ocr_team_code_normalization_handles_only_known_visual_confusions():
    assert _normalize_ocr_team_code("BOS") == "BOS"
    assert _normalize_ocr_team_code("onvk") == "NYK"
    assert _normalize_ocr_team_code("esas") == "SAS"
    assert _normalize_ocr_team_code("OKC") == "OKC"
    assert _normalize_ocr_team_code("not a team") is None


def test_fixture_status_from_luminance_has_gray_uncertainty_band():
    assert _fixture_status_from_luminance(60) is True
    assert _fixture_status_from_luminance(90) is True
    assert _fixture_status_from_luminance(100) is None
    assert _fixture_status_from_luminance(110) is False
    assert _fixture_status_from_luminance(130) is False
    assert _fixture_status_from_luminance(None) is None


def test_fixture_card_pixel_fallback_reads_each_team_on_its_own_row():
    width, height = 800, 220
    item = {"left": 280, "right": 350, "top": 90, "bottom": 190}
    pixels = bytearray([220, 220, 220] * width * height)

    def paint(left, top, right, bottom, value):
        for y in range(top, bottom):
            for x in range(left, right):
                i = (y * width + x) * 3
                pixels[i:i + 3] = bytes([value, value, value])

    paint(305, 148, 325, 155, 20)   # black top-row team name
    paint(305, 166, 325, 173, 130)  # gray second-row team name

    assert _fixture_card_pixel_status((width, height, pixels), item, 0) is True
    assert _fixture_card_pixel_status((width, height, pixels), item, 1) is False


def test_fixture_card_pixel_fallback_leaves_selected_dark_tile_unknown():
    width, height = 800, 220
    item = {"left": 280, "right": 350, "top": 90, "bottom": 190}
    pixels = bytearray([20, 20, 20] * width * height)
    for y in range(148, 155):
        for x in range(305, 325):
            i = (y * width + x) * 3
            pixels[i:i + 3] = bytes([245, 245, 245])

    assert _fixture_card_pixel_status((width, height, pixels), item, 0) is None


def test_selected_dark_fixture_tile_is_not_misread_as_black_team_text():
    width, height = 24, 12
    # Dark tile/background throughout, with a few anti-aliased white glyph
    # pixels inside the OCR rectangle. The selected fixture must remain unknown.
    pixels = bytearray([20, 20, 20] * width * height)
    for y in range(4, 8):
        for x in range(7, 14):
            if (x + y) % 2 == 0:
                idx = (y * width + x) * 3
                pixels[idx:idx + 3] = bytes([175, 175, 175])

    assert _visible_word_luminance((width, height, pixels), (6, 3, 15, 9)) is None
