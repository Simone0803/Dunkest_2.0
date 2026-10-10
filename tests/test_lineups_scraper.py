from dunkest.data.dunkest.lineups_browser import (
    _lineups_browser_profile_dir,
    _apply_lineup_annotations,
    _all_fixtures_from_accessibility_nodes,
    _annotations_from_ocr_tsv,
    _collect_lineup_annotations,
    _collect_lineup_annotations_state,
    _fixtures_from_accessibility_nodes,
    _fixture_labels_from_batches,
    _fixture_turn_map_from_batches,
    _fixture_observation,
    _fixture_present_in_market_response,
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

    assert {tuple(row.values()) for row in rows} == {
        ("Jayson Tatum", 18.0, "BOS", "A"),
        ("Joe Mazzulla", 8.0, "BOS", "HC"),
        ("Cade Cunningham", 21.0, "DET", "G"),
        ("J.B. Bickerstaff", 9.5, "DET", "HC"),
    }


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
