#!/usr/bin/env python3
"""Read-only inventory of Dunkest historical source-recovery candidates.

Filenames and fetch timestamps are not sufficient to certify pre-lock evidence.
"""
from __future__ import annotations
import argparse, csv, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AREAS = ("data/raw", "data/processed", "data/predictions", "data/archives", "data/workspaces")
PATTERNS = (
    ("fixture_mapping", re.compile(r"fixture.*mapping|mapping.*fixture", re.I)),
    ("player_market_or_credits", re.compile(r"player.?credits|opening.?market|current.?lineups.?market|listone|quotazion|market.*player", re.I)),
    ("injury_or_availability", re.compile(r"injur|availability|infortun", re.I)),
    ("coach_market_or_outcomes", re.compile(r"coach|allenator", re.I)),
    ("official_player_outcomes", re.compile(r"official.*dunkest.*player.*games|dunkest.*player.*games|dunkest_players", re.I)),
    ("lineup_or_fixture_calendar", re.compile(r"lineup|fixture|calendar|schedule|turno", re.I)),
    ("historical_week_round_stats", re.compile(r"season_\d+_week_\d+_round_\d+_", re.I)),
)
SEASON_RE = re.compile(r"(?:season[_= -]?id[_= -]?|season[_= -]?)(\d{1,2})(?:\D|$)", re.I)
WEEK_RE = re.compile(r"week[_= -]?(\d+)", re.I)
ROUND_RE = re.compile(r"round[_= -]?(\d+)", re.I)

def read_meta(path: Path) -> dict:
    meta_path = Path(str(path) + ".meta.json")
    empty = {"sidecar": "missing", "fetched_at": "", "source": "", "season_meta": "", "gameweek_meta": ""}
    if not meta_path.is_file():
        return empty
    try:
        obj = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**empty, "sidecar": "invalid"}
    return {"sidecar": "valid", "fetched_at": obj.get("fetched_at", ""),
            "source": obj.get("source", ""), "season_meta": obj.get("season_id", ""),
            "gameweek_meta": obj.get("gameweek", "")}

def family_for(name: str) -> str:
    for family, pattern in PATTERNS:
        if pattern.search(name):
            return family
    return ""

def scan(root: Path) -> list[dict]:
    rows, seen = [], set()
    for area in AREAS:
        base = root / area
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.name.endswith(".meta.json") or "__pycache__" in path.parts:
                continue
            family = family_for(path.name)
            if not family:
                continue
            rel = path.relative_to(root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            try:
                size = path.stat().st_size
                mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            except OSError:
                continue
            meta = read_meta(path)
            combined = path.name + " " + rel
            season_match, week_match, round_match = SEASON_RE.search(combined), WEEK_RE.search(combined), ROUND_RE.search(combined)
            season = meta["season_meta"] or (season_match.group(1) if season_match else "")
            week = meta["gameweek_meta"] or (week_match.group(1) if week_match else "")
            round_id = round_match.group(1) if round_match else ""
            if "data/archives/pre_lock/" in rel:
                evidence = "archive_candidate_requires_independent_review"
            elif family in {"official_player_outcomes", "historical_week_round_stats"}:
                evidence = "outcomes_or_stats_not_prelock_market"
            elif season and week and meta["fetched_at"]:
                evidence = "round_candidate_cutoff_proof_missing"
            elif season and week:
                evidence = "round_candidate_fetch_timestamp_missing"
            else:
                evidence = "season_or_round_ambiguous"
            rows.append({"path": rel, "family": family, "season_id": season,
                         "gameweek_or_week": week, "round": round_id, "size_bytes": size,
                         "modified_at_utc": mtime, **meta, "evidence_class": evidence})
    return sorted(rows, key=lambda r: (str(r["family"]), str(r["season_id"]), str(r["gameweek_or_week"]), str(r["path"])))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stamp", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    args = parser.parse_args()
    root = args.root.resolve()
    out = (args.output_dir or root / "reports" / "audit").resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = scan(root)
    csv_path = out / f"dunkest_source_recovery_inventory_{args.stamp}_v1.csv"
    md_path = out / f"dunkest_source_recovery_inventory_{args.stamp}_v1.md"
    if csv_path.exists() or md_path.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {csv_path} or {md_path}")
    fields = ["path","family","season_id","gameweek_or_week","round","size_bytes","modified_at_utc",
              "sidecar","fetched_at","source","season_meta","gameweek_meta","evidence_class"]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    families, evidence = Counter(r["family"] for r in rows), Counter(r["evidence_class"] for r in rows)
    lines = [
        "# Dunkest source-recovery inventory", "",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "Read-only filename and sidecar scan of data/raw, data/processed, data/predictions, data/archives and data/workspaces.",
        "This audit does not certify any file as pre-lock evidence.", "",
        "## Candidate files by family", "", "| Family | Files |", "|---|---:|",
    ]
    lines += [f"| {k} | {v} |" for k,v in sorted(families.items())]
    lines += ["", "## Evidence classes", "", "| Classification | Files |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in sorted(evidence.items())]
    lines += [
        "", "## Public sources reviewed", "",
        "- Dunkest listone article: https://www.dunkest.com/it/nba/notizie/fantabasket/17211/asta-fantabasket-listone-dunkest-nba",
        "- Example player page with PDK and game statistics: https://www.dunkest.com/it/giocatore/126/donte-divincenzo",
        "- Season highlights with selected PDK results, not a complete round archive: https://www.dunkest.com/it/nba/notizie/fantabasket/190007/le-migliori-prestazioni-dunkest-della-stagione-nba-2023-24",
        "- Scoring rules: https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-giocatori and https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-allenatori",
        "",
        "## Interpretation", "",
        "Outcome/stat files can support prediction evaluation but do not prove which market, credit, role or injury information was available before lock.",
        "A fetched_at timestamp records local acquisition; it is not proof of the source's original publication time or the historical lock cutoff.",
        "Do not fill missing historical market data with current pages or reconstructed injury/transfer state.",
        "Prospective archives remain eligible only after intact hashes, fresh snapshots, verified fixture identity and independent review.",
        "",
        f"Machine-readable inventory: {csv_path.relative_to(root) if csv_path.is_relative_to(root) else csv_path}", ""
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Candidate files: {len(rows)}")
    print(f"Families: {dict(sorted(families.items()))}")
    print(f"Evidence classes: {dict(sorted(evidence.items()))}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")

if __name__ == "__main__":
    main()
