from __future__ import annotations
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_recovery_audit", ROOT / "scripts/audit_dunkest_source_recovery_v1.py"
)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(audit)


def test_historical_outcomes_are_not_classified_as_prelock_market():
    assert audit.family_for("official_dunkest_player_games_2024-25_season_id_19.parquet") == "official_player_outcomes"
    assert audit.family_for("season_19_week_3_round_1_tot.parquet") == "historical_week_round_stats"


def test_round_linked_market_candidate_still_requires_cutoff_proof(tmp_path):
    root = tmp_path
    base = root / "data" / "processed"
    base.mkdir(parents=True)
    path = base / "player_credits_19_gw3.parquet"
    path.write_bytes(b"test")
    Path(str(path) + ".meta.json").write_text(json.dumps({
        "season_id": "19", "gameweek": 3,
        "fetched_at": "2026-10-14T10:00:00+00:00",
        "source": "test_source"
    }))
    rows = audit.scan(root)
    assert len(rows) == 1
    assert rows[0]["family"] == "player_market_or_credits"
    assert rows[0]["evidence_class"] == "round_candidate_cutoff_proof_missing"


def test_ambiguous_market_file_is_never_certified(tmp_path):
    root = tmp_path
    base = root / "data" / "processed"
    base.mkdir(parents=True)
    (base / "opening_market_gw1.parquet").write_bytes(b"test")
    rows = audit.scan(root)
    assert len(rows) == 1
    assert rows[0]["evidence_class"] == "season_or_round_ambiguous"
