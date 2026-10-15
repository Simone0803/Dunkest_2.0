#!/usr/bin/env python3
"""Reconcile 2026/27 Dunkest market names against the official player catalogue.

Uses the collector's conservative ID resolver plus documented official-source
probes. Similarity suggestions are for human review only and never assign IDs.
"""
from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / "data/processed/player_credits_26_gw1.parquet"
CATALOG = ROOT / "data/raw/dunkest_player_games_history_v1/player_catalog_current.json"
LINEUPS_CAPTURE = ROOT / "data/raw/dunkest_lineups_id_probe_20261012/current_lineups_market.csv"
LINEUPS_MANIFEST = ROOT / "data/raw/dunkest_lineups_id_probe_20261012/capture_manifest.json"
PROFILE_PROBE = ROOT / "data/raw/dunkest_player_games_history_v1/profile_disambiguation_probe_20261012/manifest.json"
LIVE_CATALOG_CAPTURE = ROOT / "data/raw/dunkest_player_games_history_v1/catalog_page_probe_20261012/player_catalog_page.html"
OUT = ROOT / "reports/audit"
STEM = "dunkest_current_season_id_resolution_2026-27_v2"
JSON_PATH = OUT / f"{STEM}.json"
MD_PATH = OUT / f"{STEM}.md"
CSV_PATH = OUT / f"{STEM}.csv"
SUGGESTIONS_PATH = OUT / "dunkest_current_season_id_resolution_candidates_2026-27_v2.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def load_collector():
    spec = importlib.util.spec_from_file_location(
        "dunkest_current_season_collector",
        ROOT / "scripts/collect_dunkest_player_games_current_season_v1.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the official ID resolver.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    for path in (JSON_PATH, MD_PATH, CSV_PATH, SUGGESTIONS_PATH):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite versioned output: {path}")
    OUT.mkdir(parents=True, exist_ok=True)

    collector = load_collector()
    tasks, audit, summary = collector.resolve_ids(MARKET, CATALOG)
    audit.to_csv(CSV_PATH, index=False)

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["players"]
    catalog_names = []
    for item in catalog:
        catalog_names.append({
            "id": str(item["player_id"]),
            "name": str(item.get("display_name") or ""),
            "slug_name": collector.slug_name(item.get("slug") or ""),
            "slug": str(item.get("slug") or ""),
        })

    suggestions = []
    for _, row in audit[audit["resolution"].eq("unmatched")].iterrows():
        query = norm(row["market_player_name"])
        ranked = []
        seen = set()
        for item in catalog_names:
            for candidate in (item["name"], item["slug_name"]):
                key = (item["id"], norm(candidate))
                if key in seen or not candidate:
                    continue
                seen.add(key)
                score = difflib.SequenceMatcher(None, query, norm(candidate)).ratio()
                ranked.append((score, item, candidate))
        ranked.sort(key=lambda x: x[0], reverse=True)
        top = ranked[:3]
        record = {"market_player_name": row["market_player_name"]}
        for i, (score, item, candidate) in enumerate(top, start=1):
            record[f"candidate_{i}_score"] = round(score, 3)
            record[f"candidate_{i}_name"] = candidate
            record[f"candidate_{i}_id"] = item["id"]
            record[f"candidate_{i}_slug"] = item["slug"]
        record["policy"] = "suggestion_only_no_auto_match"
        suggestions.append(record)
    pd.DataFrame(suggestions).to_csv(SUGGESTIONS_PATH, index=False)

    lineups = pd.read_csv(LINEUPS_CAPTURE)
    lineups_manifest = json.loads(LINEUPS_MANIFEST.read_text(encoding="utf-8"))
    profile_probe = json.loads(PROFILE_PROBE.read_text(encoding="utf-8"))
    page = LIVE_CATALOG_CAPTURE.read_bytes()
    page_hash = hashlib.sha256(page).hexdigest()
    live_id_set_matches = bool(lineups_manifest.get("live_catalog_id_set_matches_saved_catalog"))

    alias_counts = audit["resolution"].value_counts().to_dict()
    unresolved = audit[audit["resolution"].isin(["unmatched", "ambiguous"])]
    high_similarity = [
        r for r in suggestions
        if max(float(r.get("candidate_1_score") or 0), float(r.get("candidate_2_score") or 0)) >= 0.80
    ]
    probe_by_id = {r["player_id"]: r for r in profile_probe["records"]}
    disambiguations = [
        {
            "market_name": "Dru Smith",
            "selected_id": "1085",
            "rejected_duplicate_id": "1007",
            "selected_profile_rows_season_25": probe_by_id["1085"]["response_rows"],
            "selected_profile_valid_rows_season_25": probe_by_id["1085"]["valid_true_rows"],
            "duplicate_profile_rows_season_25": probe_by_id["1007"]["response_rows"],
            "evidence": "Official profile game-history endpoint; duplicate IDs share the same slug, but only ID 1085 has 2025/26 rows.",
        },
        {
            "market_name": "Jaylin Williams",
            "selected_id": "1115",
            "rejected_duplicate_id": "2406",
            "selected_profile_rows_season_25": probe_by_id["1115"]["response_rows"],
            "selected_profile_valid_rows_season_25": probe_by_id["1115"]["valid_true_rows"],
            "duplicate_profile_rows_season_25": probe_by_id["2406"]["response_rows"],
            "evidence": "Official profile game-history endpoint; duplicate IDs share the same slug, but only ID 1115 has 2025/26 rows.",
        },
    ]
    alias_evidence = {
        "market_name": "Elijah Harkless",
        "selected_id": "2553",
        "catalog_slug": "ej-harkless",
        "profile_url": "https://www.dunkest.com/it/giocatore/2553/ej-harkless",
        "profile_title": "EJ Harkless Stats | Dunkest",
        "season_25_game_rows": probe_by_id["2553"]["response_rows"],
        "season_25_valid_rows": probe_by_id["2553"]["valid_true_rows"],
    }

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market_path": str(MARKET.relative_to(ROOT)),
        "catalog_path": str(CATALOG.relative_to(ROOT)),
        "market_unique_names": summary["market_unique_names"],
        "resolved_unique_ids": summary["resolved_unique_ids"],
        "unmatched_names": summary["unmatched_names"],
        "ambiguous_names": summary["ambiguous_names"],
        "catalog_entries": summary["catalog_entries"],
        "resolution_method_counts": alias_counts,
        "lineups_capture": {
            "path": str(LINEUPS_CAPTURE.relative_to(ROOT)),
            "captured_at_utc": lineups_manifest.get("captured_at_utc"),
            "market_rows": len(lineups),
            "player_rows": int(lineups["role"].ne("HC").sum()),
            "coach_rows": int(lineups["role"].eq("HC").sum()),
            "has_entity_id_column": "lineups_entity_id" in lineups.columns,
            "has_entity_slug_column": "lineups_entity_slug" in lineups.columns,
            "conclusion": "The current Lineups market export exposes names, teams, roles and CR but no numeric player ID or profile slug column.",
            "capture_manifest": str(LINEUPS_MANIFEST.relative_to(ROOT)),
        },
        "live_catalog_verification": {
            "url": "https://www.dunkest.com/it/nba/giocatori",
            "profile_links": lineups_manifest.get("live_catalog_profile_links"),
            "unique_profile_ids": lineups_manifest.get("live_catalog_unique_ids"),
            "saved_catalog_unique_ids": lineups_manifest.get("saved_catalog_unique_ids"),
            "id_set_matches_saved_catalog": live_id_set_matches,
            "html_sha256": page_hash,
        },
        "resolved_duplicate_profiles": disambiguations,
        "reviewed_alias": alias_evidence,
        "unresolved_names": unresolved["market_player_name"].tolist(),
        "high_similarity_suggestions_for_manual_review": high_similarity,
        "policy": [
            "No fuzzy candidate is accepted automatically.",
            "A profile is resolved only by a unique exact/known alias or a documented explicit ID override.",
            "The 70 unmatched names remain unresolved because no unique official catalogue identity is established; many are not listed on the official player directory page.",
            "Historical endpoint rows are used only to distinguish known duplicate profiles, not as a general rule that an empty history means an ID is invalid.",
        ],
        "outputs": {
            "resolution_csv": str(CSV_PATH.relative_to(ROOT)),
            "manual_review_candidates_csv": str(SUGGESTIONS_PATH.relative_to(ROOT)),
        },
    }
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Dunkest 2026–27 Player ID Resolution Audit — V2", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        "## Resolution summary", "",
        f"- Unique market names: **{summary['market_unique_names']}**",
        f"- Resolved IDs: **{summary['resolved_unique_ids']} ({summary['resolved_unique_ids'] / summary['market_unique_names']:.1%})**",
        f"- Unmatched names: **{summary['unmatched_names']}**",
        f"- Ambiguous names remaining: **{summary['ambiguous_names']}**",
        f"- Official catalogue entries: **{summary['catalog_entries']}**", "",
        "## New resolutions", "",
        "- **Dru Smith → ID 1085**. The duplicate profile ID 1007 returns 0 rows for season 25; ID 1085 returns "
        f"{probe_by_id['1085']['response_rows']} rows, including {probe_by_id['1085']['valid_true_rows']} Dunkest-valid rows.",
        "- **Jaylin Williams → ID 1115**. The duplicate profile ID 2406 returns 0 rows for season 25; ID 1115 returns "
        f"{probe_by_id['1115']['response_rows']} rows, including {probe_by_id['1115']['valid_true_rows']} Dunkest-valid rows.",
        "- **Elijah Harkless → ID 2553** via the unique official slug ej-harkless. The official profile page title is "
        f"{alias_evidence['profile_title']}; its season-25 endpoint returns {alias_evidence['season_25_game_rows']} rows.",
        "", "## Source checks", "",
        f"- The live official player directory contains {lineups_manifest.get('live_catalog_unique_ids')} unique profile IDs; its ID set "
        f"{'matches' if live_id_set_matches else 'does not match'} the saved 1,540-entry catalogue.",
        f"- A fresh Lineups capture at {lineups_manifest.get('captured_at_utc')} contains {len(lineups)} rows "
        f"({int(lineups['role'].ne('HC').sum())} players and {int(lineups['role'].eq('HC').sum())} coaches). "
        "The exported market has no player-ID or profile-slug column, so it cannot directly resolve the remaining names.",
        "", "## Remaining unresolved names", "",
        "No fuzzy match was applied. The 70 names listed in the resolution CSV remain unresolved; a separate CSV gives up to three "
        "similarity-based candidates per name for manual inspection only. Similarity is not identity evidence.",
        "", "## Outputs", "",
        f"- Resolution audit: {CSV_PATH.relative_to(ROOT)}",
        f"- Candidate review list: {SUGGESTIONS_PATH.relative_to(ROOT)}",
        f"- Evidence JSON: {JSON_PATH.relative_to(ROOT)}",
        "", "## Safety", "",
        "The collector now includes two explicit ID overrides and one reviewed alias. No broad fuzzy matching was introduced, "
        "and no season data was collected or canonical player-game parquet overwritten by this audit.", "",
        "Re-run with: PYTHONPATH=src ./.venv/bin/python scripts/audit_dunkest_current_season_id_resolution_v2.py", "",
    ]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "report": str(MD_PATH.relative_to(ROOT)),
        "json": str(JSON_PATH.relative_to(ROOT)),
        "resolution_csv": str(CSV_PATH.relative_to(ROOT)),
        "manual_review_candidates_csv": str(SUGGESTIONS_PATH.relative_to(ROOT)),
        "resolved": summary["resolved_unique_ids"],
        "unmatched": summary["unmatched_names"],
        "ambiguous": summary["ambiguous_names"],
        "resolution_methods": alias_counts,
        "high_similarity_suggestions": len(high_similarity),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
