import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "collect_dunkest_player_games_current_season_v1",
    ROOT / "scripts" / "collect_dunkest_player_games_current_season_v1.py",
)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


def test_resolve_ids_accepts_unique_names_and_flags_missing_or_ambiguous(tmp_path):
    market = tmp_path / "market.parquet"
    pd.DataFrame({"player_name": ["Aaron Wiggins", "Dru Smith", "Unknown Prospect"]}).to_parquet(market)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"players": [
        {"player_id": "10", "slug": "aaron-wiggins", "display_name": "Wiggins Aaron"},
        {"player_id": "20", "slug": "dru-smith", "display_name": "Smith Dru"},
        {"player_id": "21", "slug": "dru-smith", "display_name": "Smith Dru"},
    ]}), encoding="utf-8")

    tasks, audit, summary = collector.resolve_ids(market, catalog)

    assert [t["player_id"] for t in tasks] == ["10"]
    assert summary["resolved_unique_ids"] == 1
    assert summary["ambiguous_names"] == 1
    assert summary["unmatched_names"] == 1
    assert set(audit["resolution"]) == {"unique_name_match", "ambiguous", "unmatched"}


def test_resolve_ids_skips_coach_roles_without_counting_them_as_unmatched(tmp_path):
    market = tmp_path / "market.csv"
    pd.DataFrame({
        "player_name": ["Aaron Wiggins", "Unknown Coach", "Another Coach"],
        "role": ["G", "HC", "HC"],
    }).to_csv(market, index=False)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"players": [
        {"player_id": "10", "slug": "aaron-wiggins", "display_name": "Wiggins Aaron"},
    ]}), encoding="utf-8")

    tasks, audit, summary = collector.resolve_ids(market, catalog)

    assert [task["player_id"] for task in tasks] == ["10"]
    assert summary["market_unique_names"] == 3
    assert summary["player_names_considered"] == 1
    assert summary["skipped_non_player_names"] == 2
    assert summary["unmatched_names"] == 0
    assert summary["ambiguous_names"] == 0
    skipped = audit[audit["resolution"].eq("skipped_non_player_role")]
    assert set(skipped["market_player_name"]) == {"Unknown Coach", "Another Coach"}
    assert set(skipped["market_role"]) == {"HC"}


def test_diagnostic_limit_never_publishes_partial_normalized_output():
    rows = pd.DataFrame({"player_id": ["10"], "pdk": [12.5]})
    assert collector.should_publish_normalized_output(rows, limit=0)
    assert not collector.should_publish_normalized_output(rows, limit=1)
    assert not collector.should_publish_normalized_output(pd.DataFrame(), limit=0)


def test_limited_or_empty_publish_leaves_existing_canonical_file_untouched(tmp_path):
    output = tmp_path / "official.parquet"
    output.write_bytes(b"frozen-canonical-content")
    original = output.read_bytes()
    rows = pd.DataFrame({"player_id": ["10"], "pdk": [12.5]})

    assert collector.publish_normalized_output(rows, output, limit=1) == "suppressed_due_to_limit"
    assert output.read_bytes() == original
    assert collector.publish_normalized_output(pd.DataFrame(), output, limit=0) == "no_rows_no_publish"
    assert output.read_bytes() == original


def test_complete_publish_writes_new_normalized_output(tmp_path):
    output = tmp_path / "nested" / "official.parquet"
    rows = pd.DataFrame({"player_id": ["10"], "pdk": [12.5]})

    assert collector.publish_normalized_output(rows, output, limit=0) == "published"
    restored = pd.read_parquet(output)
    assert restored.to_dict("records") == rows.to_dict("records")


def test_pending_tasks_refreshes_season_to_date_by_default():
    tasks = [{"player_id": str(i), "player_name": f"P{i}"} for i in range(1, 4)]
    checkpoint = {
        "1": {"status": "ok", "records": [{"gameId": "old"}]},
        "2": {"status": "empty", "records": []},
        "3": {"status": "error", "records": []},
    }

    pending = collector.select_pending_tasks(tasks, checkpoint)

    assert [task["player_id"] for task in pending] == ["1", "2", "3"]


def test_pending_tasks_can_resume_successful_checkpoint_but_retries_errors():
    tasks = [{"player_id": str(i), "player_name": f"P{i}"} for i in range(1, 4)]
    checkpoint = {
        "1": {"status": "ok", "records": [{"gameId": "old"}]},
        "2": {"status": "empty", "records": []},
        "3": {"status": "error", "records": []},
    }

    pending = collector.select_pending_tasks(tasks, checkpoint, resume=True)

    assert [task["player_id"] for task in pending] == ["3"]
    forced = collector.select_pending_tasks(tasks, checkpoint, resume=True, refresh=True, limit=2)
    assert [task["player_id"] for task in forced] == ["1", "2"]


def test_load_checkpoint_preserves_last_success_after_failed_refresh(tmp_path):
    checkpoint = tmp_path / "responses.jsonl"
    rows = [
        {"season_id": "26", "player_id": "10", "status": "ok", "records": [{"gameId": "g1", "pdk": 12.5}]},
        {"season_id": "26", "player_id": "10", "status": "error", "records": [], "error": "temporary 503"},
        {"season_id": "26", "player_id": "20", "status": "error", "records": [], "error": "still failing"},
        {"season_id": "26", "player_id": "20", "status": "ok", "records": [{"gameId": "g2", "pdk": 4.0}]},
    ]
    checkpoint.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    latest = collector.load_checkpoint(checkpoint)

    assert latest["10"]["status"] == "ok"
    assert latest["10"]["records"][0]["gameId"] == "g1"
    assert latest["20"]["status"] == "ok"
    assert latest["20"]["records"][0]["gameId"] == "g2"


def test_load_checkpoint_keeps_error_when_no_success_exists(tmp_path):
    checkpoint = tmp_path / "responses.jsonl"
    rows = [
        {"season_id": "26", "player_id": "10", "status": "error", "error": "503"},
        {"season_id": "26", "player_id": "10", "status": "error", "error": "timeout"},
    ]
    checkpoint.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    latest = collector.load_checkpoint(checkpoint)

    assert latest["10"]["status"] == "error"
    assert latest["10"]["error"] == "timeout"


def test_resolve_ids_uses_only_explicit_unique_catalogue_aliases(tmp_path):
    market = tmp_path / "market.parquet"
    pd.DataFrame({"player_name": [
        "Alex Sarr", "Ron Holland II", "Carlton Carrington",
        "Nah'shon Hyland", "Kenyon Martin Jr", "Elijah Harkless",
    ]}).to_parquet(market)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"players": [
        {"player_id": "2449", "slug": "alexandre-sarr", "display_name": "Sarr Alexandre"},
        {"player_id": "2470", "slug": "ronald-holland-ii", "display_name": "Holland II Ronald"},
        {"player_id": "2460", "slug": "bub-carrington", "display_name": "Carrington Bub"},
        {"player_id": "959", "slug": "bones-hyland", "display_name": "Hyland Bones"},
        {"player_id": "740", "slug": "kj-martin", "display_name": "Martin KJ"},
        {"player_id": "2553", "slug": "ej-harkless", "display_name": "Harkless EJ"},
    ]}), encoding="utf-8")

    tasks, audit, summary = collector.resolve_ids(market, catalog)

    assert {task["player_name"]: task["player_id"] for task in tasks} == {
        "Alex Sarr": "2449",
        "Ron Holland II": "2470",
        "Carlton Carrington": "2460",
        "Nah'shon Hyland": "959",
        "Kenyon Martin Jr": "740",
        "Elijah Harkless": "2553",
    }
    assert summary["resolved_unique_ids"] == 6
    assert audit["resolution"].eq("explicit_alias_match").sum() == 6


def test_resolve_ids_uses_reviewed_active_profile_for_duplicate_names(tmp_path):
    market = tmp_path / "market.parquet"
    pd.DataFrame({"player_name": ["Dru Smith", "Jaylin Williams"]}).to_parquet(market)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"players": [
        {"player_id": "1007", "slug": "dru-smith", "display_name": "Smith Dru"},
        {"player_id": "1085", "slug": "dru-smith", "display_name": "Smith Dru"},
        {"player_id": "1115", "slug": "jaylin-williams", "display_name": "Williams Jaylin"},
        {"player_id": "2406", "slug": "jaylin-williams", "display_name": "Williams Jaylin"},
    ]}), encoding="utf-8")

    tasks, audit, summary = collector.resolve_ids(market, catalog)

    assert {task["player_name"]: task["player_id"] for task in tasks} == {
        "Dru Smith": "1085",
        "Jaylin Williams": "1115",
    }
    assert summary["resolved_unique_ids"] == 2
    assert audit["resolution"].eq("explicit_id_override").all()


def test_normalize_results_preserves_invalid_and_unknown_validity_flags():
    latest = {
        "10": {
            "status": "ok", "player_name": "Aaron Wiggins",
            "fetched_at_utc": "2026-10-25T08:00:00+00:00",
            "records": [
                {"gameId": "dunkest-1", "gameDate": "2026-10-20", "pdk": "12.5", "gameValidForDunkest": True},
                {"gameId": "dunkest-2", "gameDate": "2026-10-22", "pdk": "8.0", "gameValidForDunkest": False},
                {"gameId": "dunkest-3", "gameDate": "2026-10-24", "pdk": "3.0", "gameValidForDunkest": None},
            ],
        }
    }

    result, _ = collector.normalize_results(latest)

    assert len(result) == 3
    assert result["gameValidForDunkest"].eq(True).sum() == 1
    assert result["gameValidForDunkest"].eq(False).sum() == 1
    assert result["gameValidForDunkest"].isna().sum() == 1
    assert set(result["_requested_player_id"]) == {"10"}


def test_normalize_results_rejects_conflicting_duplicate_player_game_keys():
    latest = {
        "10": {
            "status": "ok", "player_name": "Aaron Wiggins", "fetched_at_utc": "2026-10-25T08:00:00Z",
            "records": [
                {"gameId": "duplicate", "gameDate": "2026-10-20", "pdk": 12.5, "gameValidForDunkest": True},
                {"gameId": "duplicate", "gameDate": "2026-10-20", "pdk": 9.0, "gameValidForDunkest": True},
            ],
        }
    }

    with pytest.raises(ValueError, match="Conflicting official player-game duplicate keys"):
        collector.normalize_results(latest)


def test_identity_keys_compact_initials_and_known_nickname_variants():
    assert "ej liddell" in collector.identity_keys("E.J. Liddell")
    assert "pj washington" in collector.identity_keys("P.J. Washington")
    assert "nic claxton" in collector.identity_keys("Nicolas Claxton")
    assert "nicolas claxton" in collector.identity_keys("Nic Claxton")
