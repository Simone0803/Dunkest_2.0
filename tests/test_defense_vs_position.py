import hashlib
import json

import pandas as pd
import pytest

from dunkest.data.dunkest.defense_vs_position import (
    EXPECTED_STATS,
    EXPECTED_WINDOWS,
    SCHEMA_VERSION,
    _persist_capture_diagnostic,
    apply_dvp_pdk_adjustment,
    capture_optional_snapshot,
    inspect_source_schema,
    load_eligible_snapshot_for_cutoff,
    latest_eligible_snapshot,
    parse_dvp_table,
    season_slug,
    validate_capture,
)
from dunkest.data.dunkest.client import INJURY_TEAM_NAMES
from dunkest.config import Settings
from dunkest.report.artifacts import save_run_artifacts


def _table_html(team="Utah Jazz", rank="1", values=("30.5", "28.1", "27.0", "26.2"), duplicate=False):
    names_by_code = {}
    for name, code in INJURY_TEAM_NAMES.items():
        names_by_code.setdefault(code, name)
    names = list(names_by_code.values())
    first = f"<tr><th scope='row'>{rank}</th><td>{team}</td>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>"
    remaining = []
    for name in names:
        if name == team:
            continue
        next_rank = len(remaining) + 2
        remaining.append(
            f"<tr><th scope='row'>{next_rank}</th><td>{name}</td>"
            "<td>21.0</td><td>22.0</td><td>23.0</td><td>24.0</td></tr>"
        )
    body = first + "".join(remaining)
    if duplicate:
        body += first.replace(f">{rank}</th>", ">31</th>")
    return (
        "<table><thead><tr><th>#</th><th>Team</th>"
        "<th>L3</th><th>L5</th><th>L10</th><th>ALL</th></tr></thead><tbody>"
        + body + "</tbody></table>"
    )


def test_season_slug_and_observed_source_schema():
    assert season_slug("2026-27") == "2026-2027"
    with pytest.raises(ValueError):
        season_slug("2026-28")
    html = """<select id="seasonSelect"><option value="29">Regular Season 2026-2027</option></select>
    <select id="positionSelect"><option value="1">Guards</option><option value="2">Forwards</option><option value="3">Centers</option></select>
    <select id="statsSelect"><option value="25">Fantasy Points</option></select>
    <p>Discover the average stats and fantasy points conceded by each NBA team per position, calculated on at least 28 minutes played.</p>
    <table><thead><tr><th>#</th><th>Team</th><th>L3</th><th>L5</th><th>L10</th><th>ALL</th></tr></thead></table>"""
    schema = inspect_source_schema(html)
    assert [row["label"] for row in schema["positions"]] == ["Guards", "Forwards", "Centers"]
    assert schema["statistics"] == [{"label": "Fantasy Points", "value": "25"}]
    assert schema["headers"] == ["#", "Team", *EXPECTED_WINDOWS]
    assert "28 minutes" in schema["threshold_text"]


def test_parse_preserves_raw_values_rank_and_units_metadata():
    rows = parse_dvp_table(
        _table_html(), season_id="29", season_label="Regular Season 2026-2027",
        position="Guards", position_id="1", statistic="Fantasy Points", statistic_id="25",
        source_url="https://www.dunkest.com/en/nba/stats/teams/defense-vs-position/regular-season/2026-2027?stats_id=25&position_id=1",
        acquired_at_utc="2026-10-25T09:00:00+00:00",
    )
    assert len(rows) == 30 * 4
    assert [row["window"] for row in rows[:4]] == list(EXPECTED_WINDOWS)
    assert rows[0]["team_code"] == "UTA"
    assert rows[0]["value_original"] == "30.5"
    assert rows[0]["value"] == 30.5
    assert rows[0]["source_rank"] == 1
    assert rows[0]["source_rank_window"] == "ALL"
    assert len(rows[0]["raw_html_sha256"]) == 64


@pytest.mark.parametrize("html, message", [
    (_table_html(team="Unknown Team"), "Unmapped"),
    (_table_html(values=("30.5", "--", "27.0", "26.2")), "numeric"),
    (_table_html(duplicate=True), "Duplicate"),
    (_table_html().replace("<th>L10</th>", "<th>Last 10</th>"), "headers"),
])
def test_parse_rejects_ambiguous_incomplete_or_changed_source(html, message):
    with pytest.raises(ValueError, match=message):
        parse_dvp_table(
            html, season_id="29", season_label="Regular Season 2026-2027",
            position="Guards", position_id="1", statistic="Fantasy Points", statistic_id="25",
            source_url="https://www.dunkest.com/source", acquired_at_utc="2026-10-25T09:00:00Z",
        )


def test_validate_capture_requires_all_dimensions_and_teams():
    positions = ["Guards", "Forwards", "Centers"]
    stats = sorted(EXPECTED_STATS)
    records = []
    teams = [
        "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
    ]
    for position in positions:
        for statistic in stats:
            for rank, team in enumerate(teams, 1):
                for window in EXPECTED_WINDOWS:
                    records.append({"season_id": "29", "position": position, "statistic": statistic,
                                    "team_code": team, "window": window})
    schema = {
        "positions": [{"label": name, "value": str(i)} for i, name in enumerate(positions)],
        "statistics": [{"label": name, "value": str(i)} for i, name in enumerate(stats)],
        "headers": ["#", "Team", *EXPECTED_WINDOWS],
        "threshold_text": "calculated on at least 28 minutes played",
    }
    assert validate_capture(records, schema, "29") == []
    assert validate_capture(records[:-1], schema, "29")


def test_latest_snapshot_requires_hash_valid_complete_and_pre_cutoff(tmp_path):
    data_root = tmp_path / "processed" / "dunkest_dvp" / "29" / "capture"
    data_root.mkdir(parents=True)
    positions = ["Guards", "Forwards", "Centers"]
    statistics = sorted(EXPECTED_STATS)
    team_codes = sorted(set(INJURY_TEAM_NAMES.values()))
    frame = pd.DataFrame([
        {"season_id": "29", "position": position, "statistic": statistic,
         "schema_version": SCHEMA_VERSION, "window": window, "team_code": team,
         "value": 100.0, "source_rank": 1,
         "acquired_at_utc": "2026-10-25T07:59:00Z"}
        for position in positions for statistic in statistics
        for window in EXPECTED_WINDOWS for team in team_codes
    ])
    payload = frame.to_parquet(index=False)
    table = data_root / "records.parquet"
    table.write_bytes(payload)
    content_hash = hashlib.sha256(json.dumps(
        frame.to_dict(orient="records"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()
    manifest = {
        "schema_version": SCHEMA_VERSION, "status": "complete", "snapshot_id": "capture",
        "acquired_at_utc": "2026-10-25T07:58:00Z", "completed_at_utc": "2026-10-25T07:59:30Z",
        "records_path": "records.parquet", "positions": positions, "statistics": statistics,
        "windows": list(EXPECTED_WINDOWS), "content_sha256": content_hash,
        "records_parquet_sha256": hashlib.sha256(payload).hexdigest(), "records": len(frame),
        "source_url": "https://www.dunkest.com/source", "season_id": "29",
    }
    (data_root / "manifest.json").write_text(json.dumps(manifest))
    assert latest_eligible_snapshot(tmp_path, cutoff_utc="2026-10-25T09:00:00Z", season_id="29") is not None
    assert latest_eligible_snapshot(tmp_path, cutoff_utc="2026-10-25T07:59:30Z", season_id="29") is None
    assert latest_eligible_snapshot(tmp_path, cutoff_utc="2026-10-25T08:00:00Z", season_id="29") is not None
    assert latest_eligible_snapshot(tmp_path, cutoff_utc="2026-10-25T09:00:00Z", season_id="28") is None
    loaded, descriptor = load_eligible_snapshot_for_cutoff(
        Settings(data_dir=str(tmp_path), dunkest_stats_season_id="29"),
        cutoff_utc="2026-10-25T09:00:00Z",
    )
    assert loaded is not None and len(loaded) == len(frame)
    assert descriptor["status"] == "available"
    assert descriptor["selected_pre_cutoff"] is True
    after_cutoff, reason = load_eligible_snapshot_for_cutoff(
        Settings(data_dir=str(tmp_path), dunkest_stats_season_id="29"),
        cutoff_utc="2026-10-25T07:59:30Z",
    )
    assert after_cutoff is None
    assert reason["status"] == "unavailable"
    table.write_bytes(b"tampered")
    assert latest_eligible_snapshot(tmp_path, cutoff_utc="2026-10-25T09:00:00Z", season_id="29") is None


def test_optional_dvp_manifest_does_not_make_run_evaluable(tmp_path):
    source = tmp_path / "processed" / "dunkest_dvp" / "29" / "dvp-1" / "records.parquet"
    source.parent.mkdir(parents=True)
    source.write_bytes(pd.DataFrame([{"team_code": "UTA"}]).to_parquet(index=False))
    source_manifest = source.parent / "manifest.json"
    source_manifest.write_text(json.dumps({"status": "complete", "schema_version": SCHEMA_VERSION}))
    predictions = pd.DataFrame()
    predictions.attrs["dvp_snapshot"] = {
        "status": "applied", "selected_pre_cutoff": True, "snapshot_id": "dvp-1",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "path": str(source), "manifest_path": str(source_manifest),
        "acquired_at_utc": "2030-10-19T10:00:00Z", "records": 2880,
    }
    out = save_run_artifacts(Settings(data_dir=str(tmp_path), target_gameweek=2), predictions, [])
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["dvp_snapshot"]["snapshot_id"] == "dvp-1"
    bundled = out / manifest["dvp_snapshot"]["run_bundle_path"]
    assert bundled.is_file()
    assert hashlib.sha256(bundled.read_bytes()).hexdigest() == manifest["dvp_snapshot"]["run_bundle_sha256"]
    bundled_manifest = out / manifest["dvp_snapshot"]["run_bundle_manifest_path"]
    assert bundled_manifest.is_file()
    assert manifest["archive_status"] == "incomplete"
    assert manifest["player_forecast_snapshot"]["certification"]["pre_lock_eligible"] is False


def test_incomplete_capture_is_preserved_as_non_evaluable_diagnostic(tmp_path):
    schema = {
        "season_id": "29",
        "positions": [{"label": "Guards", "value": "1"}],
        "statistics": [{"label": "Fantasy Points", "value": "25"}],
    }
    records = [{"position": "Guards", "statistic": "Fantasy Points", "window": "L3", "team_code": "UTA"}]
    manifest_path = _persist_capture_diagnostic(
        Settings(data_dir=str(tmp_path)), source_url="https://www.dunkest.com/source",
        acquired_at="2026-10-25T09:00:00Z", status="incomplete",
        errors=["Guards/Fantasy Points: source table missing rows"], records=records, schema=schema,
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "incomplete"
    assert manifest["evaluable"] is False
    assert manifest["acquired_combinations"] == [["Guards", "Fantasy Points"]]
    assert manifest["partial_records"]["rows"] == 1
    assert manifest["errors"]
    assert latest_eligible_snapshot(tmp_path, cutoff_utc="2026-10-25T10:00:00Z", season_id="29") is None


def test_optional_capture_failure_is_explicit_but_non_blocking():
    def unavailable(_settings):
        raise OSError("browser unavailable")

    with pytest.warns(RuntimeWarning, match="continue without DvP"):
        result = capture_optional_snapshot(Settings(), collector=unavailable)
    assert result["status"] == "unavailable"
    assert "browser unavailable" in result["reason"]


def _dvp_feature_frame(utah_value=150.0):
    teams = sorted(set(INJURY_TEAM_NAMES.values()))
    return pd.DataFrame([
        {"schema_version": SCHEMA_VERSION, "season_id": "29", "position": "Guards",
         "statistic": "Fantasy Points", "window": window, "team_code": team,
         "value": utah_value if team == "UTA" else 100.0, "source_rank": 1,
         "acquired_at_utc": "2026-10-25T09:00:00Z"}
        for window in EXPECTED_WINDOWS for team in teams
    ])


def _forecast_feature_row(**overrides):
    row = {
        "player_name": "Guard One", "team": "BOS", "opponent": "UTA", "role": "G",
        "nba_game_id": "game-1", "fixture_verified": True, "expected_min": 30.0,
        "p_play": 0.8, "expected_pdk_conditional": 20.0,
        "expected_pdk_before_play_probability": 20.0, "expected_pdk": 16.0,
        "p10": 0.0, "p50": 18.0, "p90": 28.0, "pred_std": 5.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_dvp_relative_normalization_sign_cap_and_pdk_components():
    settings = Settings(dunkest_stats_season_id="29")
    positive, metadata = apply_dvp_pdk_adjustment(
        _forecast_feature_row(), _dvp_feature_frame(150.0), settings,
        snapshot_metadata={"snapshot_id": "s1", "sha256": "a" * 64, "cutoff_utc": "2026-10-25T10:00:00Z"},
    )
    assert metadata["status"] == "applied"
    assert positive.loc[0, "dvp_position"] == "Guards"
    assert positive.loc[0, "dvp_adjustment_fraction"] == pytest.approx(0.02)
    assert positive.loc[0, "expected_pdk_conditional"] == pytest.approx(20.4)
    assert positive.loc[0, "expected_pdk"] == pytest.approx(16.32)
    assert positive.loc[0, "dvp_adjustment_pdk_expected"] == pytest.approx(0.32)
    assert positive.loc[0, "p50"] == pytest.approx(18.36)
    assert positive.loc[0, "p90"] == pytest.approx(28.56)
    assert positive.loc[0, "p10"] == 0.0
    assert positive.loc[0, "expected_min"] == 30.0
    assert positive.loc[0, "p_play"] == 0.8
    assert positive.loc[0, "dvp_values_used"]
    assert metadata["validated_oos"] is False

    negative, _ = apply_dvp_pdk_adjustment(
        _forecast_feature_row(), _dvp_feature_frame(50.0), settings
    )
    assert negative.loc[0, "dvp_adjustment_fraction"] == pytest.approx(-0.02)
    assert negative.loc[0, "expected_pdk"] < 16.0


@pytest.mark.parametrize("overrides, reason", [
    ({"role": "G/F"}, "position_missing_or_ambiguous"),
    ({"opponent": "UNKNOWN"}, "opponent_unmapped"),
    ({"fixture_verified": False}, "fixture_unverified"),
    ({"nba_game_id": None}, "game_id_missing"),
])
def test_dvp_ambiguous_or_missing_mapping_falls_back_exactly(overrides, reason):
    source = _forecast_feature_row(**overrides)
    adjusted, metadata = apply_dvp_pdk_adjustment(source, _dvp_feature_frame(), Settings())
    assert adjusted.loc[0, "expected_pdk"] == source.loc[0, "expected_pdk"]
    assert adjusted.loc[0, "expected_pdk_conditional"] == source.loc[0, "expected_pdk_conditional"]
    assert adjusted.loc[0, "dvp_adjustment_fraction"] == 0.0
    assert adjusted.loc[0, "dvp_fallback_reason"] == reason
    assert metadata["covered_rows"] == 0


def test_dvp_missing_snapshot_disabled_and_missing_all_window_keep_baseline():
    settings = Settings(dunkest_stats_season_id="29")
    baseline, metadata = apply_dvp_pdk_adjustment(
        _forecast_feature_row(), None, settings,
        snapshot_metadata={"reason": "no_complete_snapshot_before_cutoff"},
    )
    assert baseline.loc[0, "expected_pdk"] == 16.0
    assert baseline.loc[0, "dvp_fallback_reason"] == "no_complete_snapshot_before_cutoff"
    assert metadata["status"] == "unavailable"

    disabled = Settings(use_dvp_matchup=False)
    baseline, metadata = apply_dvp_pdk_adjustment(
        _forecast_feature_row(), _dvp_feature_frame(), disabled
    )
    assert baseline.loc[0, "expected_pdk"] == 16.0
    assert baseline.loc[0, "dvp_fallback_reason"] == "use_dvp_matchup=false"

    missing_all = _dvp_feature_frame().query("window != 'ALL'")
    baseline, _ = apply_dvp_pdk_adjustment(_forecast_feature_row(), missing_all, settings)
    assert baseline.loc[0, "expected_pdk"] == 16.0
    assert baseline.loc[0, "dvp_fallback_reason"] == "all_window_value_missing"


def test_dvp_adjusted_expected_pdk_is_passed_to_joint_optimizer(monkeypatch):
    from types import SimpleNamespace
    from dunkest.pipeline import optimize as optimize_pipeline

    source = _forecast_feature_row()
    adjusted, _ = apply_dvp_pdk_adjustment(source, _dvp_feature_frame(), Settings())
    captured = {}
    monkeypatch.setattr(
        optimize_pipeline, "optimize_top_k_lineups",
        lambda players, coaches, settings, **kwargs: (
            captured.update(players=players.copy(), coaches=coaches.copy())
            or [SimpleNamespace(coach="Coach A", meta={}) for _ in range(3)]
        ),
    )
    coach = pd.DataFrame([{
        "coach": "Coach A", "team": "NYK", "coach_cr": 8.0,
        "expected_coach_pdk": 12.0, "win_probability": 0.62,
        "coach_projection_source": "verified_matchup", "matchup_projection_available": True,
    }])
    optimize_pipeline.run_optimize(Settings(), adjusted, coach)
    assert captured["players"].loc[0, "expected_pdk"] == pytest.approx(16.32)
    assert captured["coaches"].loc[0, "expected_coach_pdk"] == 12.0
    assert captured["coaches"].loc[0, "win_probability"] == 0.62


def test_report_exposes_dvp_status_and_fallback():
    from io import StringIO
    from rich.console import Console
    from dunkest.report.console import print_dvp_status

    output = StringIO()
    predictions = pd.DataFrame()
    predictions.attrs["dvp_snapshot"] = {
        "status": "applied", "covered_rows": 18, "player_rows": 20,
        "snapshot_id": "s1", "configured_max_relative_adjustment": 0.02,
    }
    print_dvp_status(Console(file=output, force_terminal=False), predictions)
    assert "18/20" in output.getvalue()
    assert "non validato OOS" in output.getvalue()

    output = StringIO()
    predictions.attrs["dvp_snapshot"] = {
        "status": "unavailable", "reason": "verified_cutoff_missing",
    }
    print_dvp_status(Console(file=output, force_terminal=False), predictions)
    assert "verified_cutoff_missing" in output.getvalue()
    assert "baseline" in output.getvalue()
