#!/usr/bin/env python3
"""Audit whether Lineups API entity IDs can safely resolve Dunkest profile IDs."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "data/raw/dunkest_lineups_id_probe_20261012/capture_20261012T210428Z/lineups_api_responses.json"
CATALOG = ROOT / "data/raw/dunkest_player_games_history_v1/player_catalog_current.json"
OUT = ROOT / "reports/audit"
STEM = "dunkest_lineups_internal_id_semantics_v1"
CSV_OUT = OUT / f"{STEM}.csv"
JSON_OUT = OUT / f"{STEM}.json"
MD_OUT = OUT / f"{STEM}.md"

def norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").casefold()).strip()

def main() -> int:
    for p in (CSV_OUT, JSON_OUT, MD_OUT):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite versioned output: {p}")
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["players"]
    catalog_by_id = {str(p["player_id"]): p for p in catalog}
    catalog_by_slug_name = {norm(str(p.get("slug", "")).replace("-", " ")): p for p in catalog}
    rows_by_id = {}
    identity_ids = {}
    for response in capture["responses"]:
        if response.get("status") != 200:
            continue
        data = (response.get("body") or {}).get("data") or {}
        for side in ("home_team", "away_team"):
            team = data.get(side) or {}
            team_code = str(team.get("abbreviation") or "")
            for item in team.get("lineups") or []:
                raw_id = item.get("id")
                if raw_id is None:
                    continue
                entity_id = str(raw_id)
                name = " ".join(str(item.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
                if not name:
                    name = str(item.get("name") or "").strip()
                role = str(item.get("position") or "")
                key = (team_code, norm(name), role.casefold())
                identity_ids.setdefault(key, set()).add(entity_id)
                row = rows_by_id.setdefault(entity_id, {
                    "lineups_entity_id": entity_id, "player_name": name,
                    "team_code": team_code, "position": role,
                    "quotation": item.get("quotation"), "status": item.get("status"),
                })
                if row["player_name"] != name:
                    row.setdefault("observed_names", set()).add(name)
    rows = []
    for entity_id, item in sorted(rows_by_id.items(), key=lambda kv: int(kv[0])):
        cat = catalog_by_id.get(entity_id)
        slug_match = catalog_by_slug_name.get(norm(item["player_name"]))
        rows.append({
            **item,
            "observed_names": "; ".join(sorted(item.get("observed_names", set()))),
            "same_numeric_id_in_profile_catalog": cat is not None,
            "profile_catalog_name_at_same_id": cat.get("display_name") if cat else "",
            "profile_catalog_slug_at_same_id": cat.get("slug") if cat else "",
            "name_matches_profile_catalog_slug": slug_match is not None,
            "name_matched_profile_id": str(slug_match["player_id"]) if slug_match else "",
            "name_matched_profile_slug": slug_match["slug"] if slug_match else "",
            "identity_warning": "Lineups entity ID is not a profile ID unless independently verified",
        })
    df = pd.DataFrame(rows)
    df.to_csv(CSV_OUT, index=False)
    overlaps = df[df["same_numeric_id_in_profile_catalog"]]
    same_name_at_same_id = int((overlaps["player_name"].map(norm) == overlaps["profile_catalog_slug_at_same_id"].map(lambda s: norm(str(s).replace("-", " ")))).sum())
    matched_names = int(df["name_matches_profile_catalog_slug"].sum())
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "capture_path": str(CAPTURE.relative_to(ROOT)),
        "capture_sha256": hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
        "catalog_path": str(CATALOG.relative_to(ROOT)),
        "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "api_responses": len(capture["responses"]),
        "http_200_responses": sum(r.get("status") == 200 for r in capture["responses"]),
        "unique_lineups_entity_ids": int(df["lineups_entity_id"].nunique()),
        "unique_entities_with_same_numeric_id_in_profile_catalog": int(df["same_numeric_id_in_profile_catalog"].sum()),
        "same_name_at_same_numeric_id": same_name_at_same_id,
        "exact_profile_slug_name_matches": matched_names,
        "entities_without_profile_slug_name_match": int((~df["name_matches_profile_catalog_slug"]).sum()),
        "ids_per_team_name_role_identity_max": max((len(v) for v in identity_ids.values()), default=0),
        "conclusion": (
            "The Lineups API field id is a Lineups entity identifier, not a Dunkest player-profile ID. "
            "Numeric overlap with the profile catalogue is not sufficient evidence: this capture has "
            f"{int(df['same_numeric_id_in_profile_catalog'].sum())} overlapping numeric IDs but {same_name_at_same_id} "
            "same-player matches at those IDs. Do not use Lineups id to query /api/player/games. "
            "Resolve historical player-game IDs only from the official profile catalogue or a verified profile URL."
        ),
        "policy": [
            "No Lineups entity ID is written into the official Dunkest player ID field.",
            "Names matched to profile slugs are a separate matching dimension.",
            "Unmatched rookies remain unresolved until a profile ID is published or an explicit official cross-reference is available.",
        ],
        "csv": str(CSV_OUT.relative_to(ROOT)),
    }
    JSON_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Lineups API ID semantics audit — V1", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        "## Results", "",
        f"- API responses captured: **{result['api_responses']}** ({result['http_200_responses']} successful)",
        f"- Unique Lineups entity IDs: **{result['unique_lineups_entity_ids']}**",
        f"- IDs numerically overlapping profile catalogue: **{result['unique_entities_with_same_numeric_id_in_profile_catalog']}**",
        f"- Same-player matches at the same numeric ID: **{result['same_name_at_same_numeric_id']}**",
        f"- Names matching an official profile slug: **{result['exact_profile_slug_name_matches']}**",
        f"- Names without an exact profile-slug match: **{result['entities_without_profile_slug_name_match']}**", "",
        "## Conclusion", "", result["conclusion"], "",
        "## Safety policy", "", *[f"- {x}" for x in result["policy"]], "",
        "Detailed rows: " + str(CSV_OUT.relative_to(ROOT)), "",
        "Reproduce with: PYTHONPATH=src ./.venv/bin/python scripts/audit_dunkest_lineups_internal_id_semantics_v1.py", "",
    ]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"policy","conclusion"}}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
