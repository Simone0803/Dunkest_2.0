#!/usr/bin/env python3
"""Read-only audit of historical evidence required for complete-lineup backtests."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
OUT = ROOT / "reports/audit"
JSON_PATH = OUT / "dunkest_lineup_backtest_readiness_v2.json"
MD_PATH = OUT / "dunkest_lineup_backtest_readiness_v2.md"
PATTERNS = {
    "player_results": re.compile(r"dunkest_players_(\d+)_gw(\d+)\.parquet$"),
    "player_credits": re.compile(r"player_credits_(\d+)_gw(\d+)\.parquet$"),
    "coach_market": re.compile(r"coach_market_(\d+)_gw(\d+)\.parquet$"),
    "injuries": re.compile(r"injuries_(\d+)_gw(\d+)\.parquet$"),
    "coach_results": re.compile(r"dunkest_coach_results_(\d+)_gw(\d+)\.parquet$"),
}

def columns(path):
    try:
        return set(pq.ParquetFile(path).schema.names)
    except Exception:
        return set()

def metadata(path):
    if path is None:
        return {}
    meta_path = Path(str(path) + ".meta.json")
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except Exception:
        return {}

def inventory(pattern):
    found = {}
    for p in PROCESSED.glob("*.parquet"):
        m = pattern.fullmatch(p.name)
        if m:
            found[(m.group(1), int(m.group(2)))] = p
    return found

def main():
    if JSON_PATH.exists() or MD_PATH.exists():
        raise SystemExit("Refusing to overwrite versioned outputs.")
    OUT.mkdir(parents=True, exist_ok=True)
    files = {k: inventory(v) for k, v in PATTERNS.items()}
    mappings = {}
    for p in PROCESSED.glob("dunkest_fixture_mapping_*.parquet"):
        m = re.search(r"dunkest_fixture_mapping_(\d+)_", p.name)
        if m:
            mappings.setdefault(m.group(1), []).append(p)
    seasons = sorted({sid for inv in files.values() for sid, _ in inv} | set(mappings), key=int)
    rounds = []
    for sid in seasons:
        gws = sorted({gw for inv in files.values() for s, gw in inv if s == sid})
        map_paths = sorted(mappings.get(sid, []))
        for gw in gws:
            paths = {k: v.get((sid, gw)) for k, v in files.items()}
            mp = map_paths[-1] if map_paths else None
            mc = columns(mp) if mp else set()
            pc = columns(paths["player_credits"]) if paths["player_credits"] else set()
            ic = columns(paths["injuries"]) if paths["injuries"] else set()
            cc = columns(paths["coach_market"]) if paths["coach_market"] else set()
            rc = columns(paths["player_results"]) if paths["player_results"] else set()
            crc = columns(paths["coach_results"]) if paths["coach_results"] else set()
            import pandas as pd
            mapping_ok = False
            mapping_df = pd.DataFrame()
            cutoff = pd.NaT
            if mp and {"nba_game_id","mapping_verified","source_retrieved_at_utc","raw_payload_sha256","game_datetime_utc"}.issubset(mc):
                mapping_df = pd.read_parquet(mp)
                mapping_df["game_datetime_utc"] = pd.to_datetime(mapping_df["game_datetime_utc"], errors="coerce", utc=True)
                mapping_df["source_retrieved_at_utc"] = pd.to_datetime(mapping_df["source_retrieved_at_utc"], errors="coerce", utc=True)
                cutoff = mapping_df["game_datetime_utc"].min()
                mapping_ok = bool(not mapping_df.empty and mapping_df["mapping_verified"].fillna(False).astype(bool).all()
                    and mapping_df["source_retrieved_at_utc"].notna().all()
                    and mapping_df["source_retrieved_at_utc"].le(mapping_df["game_datetime_utc"]).all()
                    and mapping_df["raw_payload_sha256"].astype(str).str.strip().ne("").all())
            credits_meta = metadata(paths["player_credits"])
            injuries_meta = metadata(paths["injuries"])
            coach_meta = metadata(paths["coach_market"])
            def captured_before_tipoff(meta):
                ts = pd.to_datetime(meta.get("fetched_at") or meta.get("captured_at_utc"), errors="coerce", utc=True)
                return bool(pd.notna(ts) and pd.notna(cutoff) and ts <= cutoff)
            credits_ok = bool(paths["player_credits"] and {"player_name","team_code","role","gameweek","cr"}.issubset(pc)
                and captured_before_tipoff(credits_meta))
            injuries_ok = bool(paths["injuries"] and {"player_name","team","status","gameweek"}.issubset(ic)
                and captured_before_tipoff(injuries_meta))
            coach_ok = bool(paths["coach_market"] and {"coach","team","coach_cr","opponent","date","nba_game_id","fixture_source"}.issubset(cc)
                and captured_before_tipoff(coach_meta)
                and set(pd.read_parquet(paths["coach_market"])["nba_game_id"].astype(str)).issubset(set(mapping_df.get("nba_game_id", pd.Series(dtype=str)).astype(str))))
            player_result_ok = False
            player_result_reason = "missing player results"
            if paths["player_results"] and {"player_name","actual_pdk","gameweek_stats_available","nba_game_id"}.issubset(rc):
                import pandas as pd
                actuals = pd.read_parquet(paths["player_results"])
                if not actuals["gameweek_stats_available"].fillna(False).astype(bool).any():
                    player_result_reason = "no rows marked realized"
                elif pd.to_numeric(actuals["actual_pdk"], errors="coerce").notna().sum() == 0:
                    player_result_reason = "no finite actual PDK"
                elif not mp or "nba_game_id" not in mc:
                    player_result_reason = "no fixture mapping for linkage"
                else:
                    allowed = set(mapping_df.get("nba_game_id", pd.Series(dtype=str)).astype(str))
                    player_result_ok = bool(actuals["nba_game_id"].astype(str).isin(allowed).all()
                        and actuals["gameweek_stats_available"].fillna(False).astype(bool).any()
                        and pd.to_numeric(actuals["actual_pdk"], errors="coerce").notna().any())
                    player_result_reason = "linked" if player_result_ok else "results do not link to mapping IDs"
            coach_result_ok = False
            if paths["coach_results"] and {"team","nba_game_id","actual_coach_pdk"}.issubset(crc) and not mapping_df.empty:
                coach_actuals = pd.read_parquet(paths["coach_results"])
                coach_result_ok = bool(coach_actuals["nba_game_id"].astype(str).isin(set(mapping_df["nba_game_id"].astype(str))).all()
                    and pd.to_numeric(coach_actuals["actual_coach_pdk"], errors="coerce").notna().any())
            checks = {"fixture_mapping":mapping_ok,"roster_and_CR":credits_ok,"timestamped_injuries":injuries_ok,
                      "fixture_linked_coaches":coach_ok,"player_results_linked":player_result_ok,
                      "coach_results_linked":coach_result_ok}
            rounds.append({"season_id":sid,"gameweek":gw,"checks":checks,
                "ready_for_full_lineup_backtest":all(checks.values()),"player_result_reason":player_result_reason,
                "files":{k:(str(p.relative_to(ROOT)) if p else None) for k,p in paths.items()},
                "fixture_mapping":str(mp.relative_to(ROOT)) if mp else None})
    snapshot_runs = []
    for d in sorted((DATA/"predictions").glob("*/pre_match_snapshot")):
        snapshot_runs.append({"run_id":d.parent.name,"files":sorted(p.name for p in d.iterdir() if p.is_file())})
    ready = [r for r in rounds if r["ready_for_full_lineup_backtest"]]
    check_names = list(rounds[0]["checks"]) if rounds else []
    result = {"generated_at_utc":datetime.now(timezone.utc).isoformat(),"season_ids_scanned":seasons,
        "rounds_scanned":len(rounds),"rounds_ready":len(ready),"rounds_not_ready":len(rounds)-len(ready),
        "checks_passed_by_type":{k:sum(bool(r["checks"][k]) for r in rounds) for k in check_names},
        "rounds":rounds,"pre_match_snapshot_run_count":len(snapshot_runs),"pre_match_snapshot_runs":snapshot_runs,
        "conclusion":("At least one round meets file/schema gates; run the production readiness validator before scoring." if ready else
          "No scanned round has all required archived inputs. Valid complete-lineup metrics cannot be computed without inventing pre-game state or using look-ahead data."),
        "policy":"Raw archives untouched. Same-round weekly CR/PDK tables are not treated as verified pre-game snapshots. Missing actuals are never scored as zero."}
    JSON_PATH.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=["# Dunkest complete-lineup backtest readiness audit — V2","",f"Generated (UTC): {result['generated_at_utc']}","",
        "## Summary","",f"- Season IDs scanned: {', '.join(seasons) if seasons else 'none'}",
        f"- Round records scanned: {len(rounds)}",f"- Rounds ready for full-lineup backtest: **{len(ready)}**",
        f"- Rounds not ready: {len(rounds)-len(ready)}","","| Input evidence | Rounds passing |","|---|---:|"]
    for k,v in result["checks_passed_by_type"].items():
        lines.append(f"| {k.replace('_',' ')} | {v}/{len(rounds)} |")
    lines += ["","## Round-level status","","| Season ID | GW | Mapping | Roster/CR | Injuries | Coaches | Player results | Coach results |","|---:|---:|---|---|---|---|---|---|"]
    for r in rounds:
        c=r["checks"]
        lines.append("| "+" | ".join([r["season_id"],str(r["gameweek"])]+["OK" if c[k] else "missing/invalid" for k in check_names])+" |")
    lines += ["","## Interpretation","",result["conclusion"],"",
        "The production command was run for season 2025-26, GW1–10. It returned Backtest non pronto — nessuna metrica lineup prodotta because fixture mapping, roster/CR snapshots, timestamped injury snapshots, fixture-linked coach snapshots and linked player/coach outcomes are missing or unproven.","",
        "Historical weekly archives contain round outcomes but do not establish which prices, injuries, availability and coach market were known before tip-off. Using same-round data would introduce look-ahead bias.","",
        "## Required capture for future rounds","",
        "For each upcoming gameweek, retain an immutable pre-match bundle with: verified fixture mapping (source, retrieval time and payload hash); full player roster and CR; timestamped injuries/availability; coach market linked to NBA fixture IDs; and model predictions generated before tip-off. After games finish, append realized player and coach scores linked to those same fixture IDs. Version every recapture and never overwrite raw snapshots.","",
        "## Reproducibility","","    PYTHONPATH=$PWD/src ./.venv/bin/python scripts/audit_dunkest_lineup_backtest_readiness_v1.py",""]
    MD_PATH.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"json":str(JSON_PATH.relative_to(ROOT)),"markdown":str(MD_PATH.relative_to(ROOT)),
        "season_ids_scanned":seasons,"rounds_scanned":len(rounds),"rounds_ready":len(ready),
        "rounds_not_ready":len(rounds)-len(ready),"checks_passed_by_type":result["checks_passed_by_type"],
        "pre_match_snapshot_runs":len(snapshot_runs)},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
