from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

import pandas as pd

from dunkest.backtest.walk_forward import run_walk_forward_backtest
from dunkest.backtest.metrics import compute_lineup_coverage
from dunkest.config import Settings, load_roster_yaml
from dunkest.pipeline.collect import run_collect
from dunkest.pipeline.optimize import run_optimize
from dunkest.pipeline.predict import run_predict
from dunkest.pipeline.train import run_train
from dunkest.report.artifacts import save_run_artifacts
from dunkest.report.console import print_matchday_report
from dunkest.report.season_opener import print_season_opener_report
from dunkest.report.terminal import CONSOLE, print_dataframe, print_header
from dunkest.pipeline.season_opener import run_season_opener
from dunkest.names import player_key


def _archive_and_review_run(run_dir: Path, data_dir: Path) -> dict:
    """Seal a saved run and recheck it without changing its eligibility gates."""
    repo_root = Path(__file__).resolve().parents[2]
    archive_root = data_dir.expanduser().resolve() / "archives" / "pre_lock"
    archive_script = repo_root / "scripts" / "archive_dunkest_pre_lock_run_v1.py"
    review_script = repo_root / "scripts" / "review_dunkest_pre_lock_archive_v1.py"

    try:
        archived = subprocess.run(
            [
                sys.executable,
                str(archive_script),
                "--run-dir",
                str(run_dir.resolve()),
                "--archive-root",
                str(archive_root),
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {"status": "archive_failed", "error": str(exc)}
    if archived.returncode != 0:
        return {
            "status": "archive_failed",
            "error": (archived.stderr or archived.stdout).strip()[-2000:],
        }
    try:
        archive_result = json.loads(archived.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        return {"status": "archive_failed", "error": f"invalid archiver response: {exc}"}
    archive_path = archive_result.get("archive_path")
    if not archive_path:
        return {"status": "archive_failed", "error": "archiver response has no archive_path"}

    try:
        reviewed = subprocess.run(
            [
                sys.executable,
                str(review_script),
                "--archive-dir",
                str(Path(archive_path).resolve()),
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {"status": "review_failed", "archive": archive_result, "error": str(exc)}
    if reviewed.returncode != 0:
        return {
            "status": "review_failed",
            "archive": archive_result,
            "error": (reviewed.stderr or reviewed.stdout).strip()[-2000:],
        }
    try:
        review_result = json.loads(reviewed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        return {
            "status": "review_failed",
            "archive": archive_result,
            "error": f"invalid reviewer response: {exc}",
        }
    return {"status": "reviewed", "archive": archive_result, "review": review_result}


def _report_archive_review(archive_check: dict) -> None:
    """Report archive status; fail the command only for technical archive/review errors."""
    if archive_check.get("status") != "reviewed":
        CONSOLE.print(
            "[bold yellow]Archivio pre-lock non verificato[/bold yellow]  "
            f"{archive_check.get('error', archive_check.get('status', 'unknown_error'))}. "
            "Il forecast è stato salvato, ma non va considerato eleggibile."
        )
        raise SystemExit(2)

    archived = archive_check["archive"]
    reviewed = archive_check["review"]
    if archived.get("pre_lock_eligible") and reviewed.get("rechecked_pre_lock_eligible"):
        CONSOLE.print(
            "[bold green]Bundle pre-lock verificato[/bold green]  "
            f"{archived.get('archive_path')}"
        )
    else:
        CONSOLE.print(
            "[bold yellow]Bundle archiviato a fini diagnostici, non eleggibile[/bold yellow]  "
            f"stato reviewer: {reviewed.get('status')}; "
            f"eligibility: {archived.get('eligibility_status')}; "
            f"archivio: {archived.get('archive_path')}"
        )


def _prepare_and_open_current_roster(roster_path: Path) -> None:
    """Open the current roster for editing before a post-opener run."""
    roster_path = roster_path.expanduser().resolve()
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    if not roster_path.exists():
        example = Path(__file__).resolve().parents[2] / "config" / "roster.example.yaml"
        if example.is_file():
            shutil.copyfile(example, roster_path)
        else:
            roster_path.write_text(
                "budget: null # inserisci il budget CR totale attuale\n"
                "players:\n  - Inserisci nome giocatore 1\n"
                "coach: Inserisci nome coach\n",
                encoding="utf-8",
            )

    # A configured editor can be a terminal editor (EDITOR=nano) or a GUI
    # editor with a wait option (for example VISUAL="code --wait").
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.run([*shlex.split(editor), str(roster_path)], check=False)
        return

    if sys.platform == "darwin":
        opener = ["open", "-t", str(roster_path)]
    elif os.name == "nt":
        os.startfile(str(roster_path))  # type: ignore[attr-defined]
        opener = []
    else:
        opener = ["xdg-open", str(roster_path)]

    if opener:
        subprocess.Popen(opener)
    if sys.stdin.isatty():
        input(f"\nModifica e salva {roster_path}, poi premi Invio per continuare... ")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dunkest")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="Fetch and cache data")
    p_collect.add_argument("--season", default=None)
    p_collect.add_argument("--force", action="store_true")

    p_run = sub.add_parser("run", help="Predict and optimize next gameweek")
    p_run.add_argument("--giornata", type=int, required=True)
    p_run.add_argument("--turno", type=int, default=None, help="Compatibilità legacy; lo scraping acquisisce sempre l'intera Giornata")
    p_run.add_argument(
        "--budget", type=float, default=None,
        help="sovrascrive il budget letto dal file rosa",
    )
    p_run.add_argument("--roster", type=Path, default=None)
    p_run.add_argument("--transfer-penalty", type=float, default=None)
    p_run.add_argument("--config", type=Path, default=None)
    p_run.add_argument(
        "--no-lineups-scrape",
        action="store_true",
        help="Usa il market già salvato e non apre il browser autenticato",
    )

    p_open = sub.add_parser(
        "season-opener",
        help="Giornata 1 — nuova squadra (95 CR, forma della stagione NBA precedente)",
    )
    p_open.add_argument("--config", type=Path, default=None)
    p_open.add_argument(
        "--credits-file",
        type=Path,
        default=None,
        help="CSV con player_name, cr (quotazioni ufficiali della stagione target)",
    )
    p_open.add_argument("--budget", type=float, default=95.0)
    p_open.add_argument("--turno", type=int, default=None, help="Compatibilità legacy; lo scraping acquisisce sempre l'intera Giornata 1")
    p_open.add_argument(
        "--official-cr-only",
        action="store_true",
        help="Ignora eventuali quotazioni stimate e usa solo CR presenti nei dati/CSV",
    )
    p_open.add_argument(
        "--estimate-credits",
        action="store_true",
        help="Consenti un CR proxy basato sui PDK storici (squadre solo indicative)",
    )
    p_open.add_argument("--force-refresh", action="store_true")
    p_open.add_argument(
        "--no-lineups-scrape",
        action="store_true",
        help="Usa il market indicato o già salvato senza aprire Lineups",
    )
    p_open.add_argument(
        "--prior-season",
        default=None,
        help="Stagione NBA per feature / forma",
    )

    p_bt = sub.add_parser("backtest", help="Walk-forward backtest")
    p_bt.add_argument("--from-gw", type=int, default=10)
    p_bt.add_argument("--to-gw", type=int, default=20)
    p_bt.add_argument("--config", type=Path, default=None)

    args = parser.parse_args()
    cfg_path = getattr(args, "config", None)
    settings = Settings.from_yaml(cfg_path) if cfg_path else Settings.from_yaml()

    if args.command == "season-opener":
        cfg = args.config or (Settings.from_yaml().root / "config" / "season_opener.yaml")
        settings = Settings.from_yaml(cfg) if cfg.exists() else Settings.from_yaml()
        # The scraper captures the complete Dunkest Gameweek 1 in one browser
        # session; --turno remains accepted only for backward CLI compatibility.
        settings.target_dunkest_turn = None
        settings.budget = args.budget
        if args.prior_season:
            settings.feature_season = args.prior_season
        if args.official_cr_only:
            settings.opening_use_pdk_cr_proxy = False
        if args.estimate_credits:
            settings.opening_use_pdk_cr_proxy = True
        credits_file = args.credits_file
        if credits_file is None:
            credits_file = settings.data_path / "current_lineups_market.csv"
            if not args.no_lineups_scrape:
                try:
                    from dunkest.data.dunkest.lineups_browser import scrape_lineups_market

                    print("\nAcquisizione Lineups dell'intera Giornata 1...")
                    scrape_lineups_market(credits_file, turn_number=None)
                    capture_manifest = {
                        "source": "dunkest_lineups_browser",
                        "gameweek": 1,
                        "capture_scope": "full_gameweek_all_turns",
                        "turns_captured": [1, 2, 3],
                        "market_merged": False,
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                    }
                    (settings.data_path / "lineups_gw1_capture.json").write_text(
                        json.dumps(capture_manifest, indent=2), encoding="utf-8"
                    )
                except Exception as exc:
                    parser.error(f"Scraping Lineups non riuscito: {exc}")
        elif not credits_file.exists():
            parser.error(f"File quotazioni non trovato: {credits_file}")
        try:
            preds, coach_df, market, solutions, meta = run_season_opener(
                settings,
                credits_file=credits_file,
                force_refresh=args.force_refresh,
            )
        except (RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print_season_opener_report(settings, preds, market, coach_df, solutions, meta)
        out = save_run_artifacts(
            settings,
            preds,
            solutions,
            meta.get("model_artifact_metadata"),
            run_metadata={key: value for key, value in meta.items() if key != "model_artifact_metadata"},
            coach_forecasts=coach_df,
        )
        market.to_parquet(out / "opening_market.parquet", index=False)
        coach_df.to_parquet(out / "coach_predictions.parquet", index=False)
        CONSOLE.print(f"\n[bold green]Artefatti salvati[/bold green]  {out}")
        return

    if args.command == "collect":
        if args.season:
            settings.season = args.season
        summary = run_collect(settings, force_refresh=args.force)
        print_header(CONSOLE, "RACCOLTA COMPLETATA", f"Stagione NBA {settings.season}")
        print_dataframe(
            CONSOLE,
            "Dataset aggiornati",
            pd.DataFrame([{"dataset": name, "rows": count} for name, count in summary.items()]),
            [("dataset", "Dataset", None), ("rows", "Righe", "d")],
        )
        return

    if args.command == "run":
        settings.target_gameweek = args.giornata
        # The Lineups scraper always captures the complete gameweek in one
        # browser session; --turno is accepted only for backward compatibility.
        settings.target_dunkest_turn = None
        if args.budget is not None:
            if not isfinite(args.budget) or args.budget <= 0:
                parser.error("--budget deve essere un numero finito e maggiore di zero")
            settings.budget = args.budget
        roster_path = args.roster
        open_roster_editor = False
        if args.giornata > 1 and roster_path is None:
            # Interactive runs default to the editable local roster file.
            # Non-interactive/scripted runs retain an explicit --roster requirement.
            if not sys.stdin.isatty():
                parser.error(
                    "dalla giornata 2 devi indicare --roster con i 10 giocatori e il coach attuali"
                )
            roster_path = Path("config/current_roster.yaml")
            open_roster_editor = True
        if open_roster_editor:
            try:
                _prepare_and_open_current_roster(roster_path)
            except (OSError, subprocess.SubprocessError) as exc:
                parser.error(f"impossibile aprire il file della rosa {roster_path}: {exc}")
        if roster_path:
            try:
                players, coach, roster_budget = load_roster_yaml(roster_path)
            except (OSError, ValueError, TypeError) as exc:
                parser.error(f"file rosa non valido ({roster_path}): {exc}")
            if args.giornata > 1:
                if len(players) != 10 or not isinstance(coach, str) or not coach.strip():
                    parser.error("il file --roster deve contenere esattamente 10 giocatori e il coach attuale")
                normalized = [player_key(p) for p in players]
                if any(not name for name in normalized) or len(set(normalized)) != 10:
                    parser.error("la rosa attuale contiene nomi vuoti o giocatori duplicati dopo la normalizzazione")
                if args.budget is None:
                    try:
                        budget = float(roster_budget)
                    except (TypeError, ValueError):
                        parser.error(
                            f"aggiungi 'budget: <CR totali>' a {roster_path} oppure passa --budget"
                        )
                    if not isfinite(budget) or budget <= 0:
                        parser.error(
                            f"il budget in {roster_path} deve essere finito e maggiore di zero"
                        )
                    settings.budget = budget
            players = [str(player).strip() for player in players]
            settings.current_roster = players
            settings.current_coach = str(coach).strip() if isinstance(coach, str) and coach.strip() else None
        if not args.no_lineups_scrape:
            try:
                from dunkest.data.dunkest.lineups_browser import scrape_lineups_market
                from dunkest.data.dunkest.fixtures import save_current_capture_fixture_mapping

                market_path = settings.data_path / "current_lineups_market.csv"
                previous_market = market_path.read_bytes() if market_path.is_file() else None
                market_metadata_path = market_path.with_suffix(market_path.suffix + ".meta.json")
                previous_market_metadata = (
                    market_metadata_path.read_bytes() if market_metadata_path.is_file() else None
                )
                print(f"\nAcquisizione Lineups dell'intera Giornata {args.giornata} (tutti i turni)...")
                try:
                    scrape_lineups_market(market_path, turn_number=None)
                    mapping = save_current_capture_fixture_mapping(settings, args.giornata)
                    if mapping.empty:
                        raise RuntimeError(
                            f"Nessun matchup verificato per la Giornata {args.giornata}; "
                            "non genero rose su un calendario incompleto."
                        )
                except Exception:
                    # A valid market is kept until the new fixture capture has
                    # been certified for the requested gameweek.
                    if previous_market is not None:
                        market_path.write_bytes(previous_market)
                    elif market_path.is_file():
                        market_path.unlink()
                    if previous_market_metadata is not None:
                        market_metadata_path.write_bytes(previous_market_metadata)
                    elif market_metadata_path.is_file():
                        market_metadata_path.unlink()
                    raise
                capture_manifest = {
                    "source": "dunkest_lineups_browser",
                    "gameweek": args.giornata,
                    "capture_scope": "full_gameweek_all_turns",
                    "turns_captured": [1, 2, 3],
                    "market_merged": False,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "fixture_mapping_rows": int(len(mapping)),
                    "fixture_mapping_verified": True,
                }
                (settings.data_path / f"lineups_gw{args.giornata}_capture.json").write_text(
                    json.dumps(capture_manifest, indent=2), encoding="utf-8"
                )
            except Exception as exc:
                parser.error(f"Aggiornamento Lineups/calendario non riuscito: {exc}")
        else:
            from dunkest.data.dunkest.fixtures import get_fixture_mapping

            mapping = get_fixture_mapping(settings, args.giornata)
            if mapping.empty:
                parser.error(
                    f"Manca una mappatura fixture verificata per la Giornata {args.giornata}. "
                    "Rimuovi --no-lineups-scrape per acquisire mercato e calendario completi."
                )
        if args.giornata > 1:
            settings.transfer_penalty = 5.0 if args.transfer_penalty is None else args.transfer_penalty
        elif args.transfer_penalty is not None:
            settings.transfer_penalty = args.transfer_penalty
        models, features = run_train(settings)
        preds, coach_df = run_predict(settings, models, features)
        try:
            solutions = run_optimize(settings, preds, coach_df)
        except (RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        for i, sol in enumerate(solutions, start=1):
            sol.rank = i
        print_matchday_report(settings, preds, coach_df, solutions)
        out = save_run_artifacts(
            settings, preds, solutions, models, coach_forecasts=coach_df
        )
        CONSOLE.print(f"\n[bold green]Artefatti salvati[/bold green]  {out}")
        archive_check = _archive_and_review_run(out, settings.data_path)
        _report_archive_review(archive_check)
        return

    if args.command == "backtest":
        results, report, extras = run_walk_forward_backtest(settings, args.from_gw, args.to_gw)
        print_header(
            CONSOLE,
            "WALK-FORWARD BACKTEST",
            f"Stagione {settings.season}  |  Giornate {args.from_gw}-{args.to_gw}",
        )
        if not extras.get("backtest_ready", False):
            readiness_rows = []
            for gw, evidence in extras.get("readiness", {}).items():
                for name, check in evidence.get("checks", {}).items():
                    readiness_rows.append({
                        "gameweek": gw,
                        "check": name,
                        "status": "PASS" if check["pass"] else "FAIL",
                        "details": check["reason"],
                    })
            print_dataframe(
                CONSOLE,
                "Backtest non pronto — nessuna metrica lineup prodotta",
                pd.DataFrame(readiness_rows),
                [("gameweek", "GW", "d"), ("check", "Controllo", None),
                 ("status", "Esito", None), ("details", "Evidenza", None)],
                max_rows=100,
            )
            raise SystemExit(2)
        metrics = pd.DataFrame(
            [
                {"metric": "Player score medio", "value": report.average_player_score},
                {"metric": "Player score mediano", "value": report.median_player_score},
                {"metric": "Punteggio squadra reale medio", "value": report.average_team_score},
                {"metric": "Punteggio squadra reale mediano", "value": report.median_team_score},
                {"metric": "Best-of-3 player score", "value": report.best_of_3_player_score},
                {"metric": "Top-1 vs oracle player", "value": report.top1_hit_rate},
                {"metric": "Top-3 include oracle", "value": report.top3_hit_rate},
                {"metric": "Regret vs optimum player", "value": report.regret_vs_ex_post_player_score},
                {"metric": "Accuratezza capitano", "value": report.captain_accuracy},
                {"metric": "Trasferimenti medi", "value": report.average_transfers},
            ]
        )
        percentage_metrics = {
            "Top-1 vs oracle player", "Top-3 include oracle", "Accuratezza capitano"
        }
        metrics["value_display"] = [
            format(value, ".1%" if metric in percentage_metrics else ".2f")
            if pd.notna(value) else "n/d"
            for metric, value in zip(metrics["metric"], metrics["value"])
        ]
        print_dataframe(
            CONSOLE,
            "Metriche disponibili",
            metrics,
            [("metric", "Metrica", None), ("value_display", "Valore", None)],
        )
        lineup_coverage = compute_lineup_coverage(
            results, list(range(args.from_gw, args.to_gw + 1))
        )
        coverage_rows = [
            {
                "copertura": "Giornate richieste con risultati",
                "conteggio": f"{lineup_coverage['gameweeks_with_results']} / {lineup_coverage['requested_gameweeks']}",
            },
            {
                "copertura": "GW con score completo della rosa #1",
                "conteggio": f"{lineup_coverage['gameweeks_with_complete_rank1']} / {lineup_coverage['requested_gameweeks']}",
            },
            {
                "copertura": "GW con tre score lineup completi",
                "conteggio": f"{lineup_coverage['gameweeks_with_three_complete_lineups']} / {lineup_coverage['requested_gameweeks']}",
            },
            {
                "copertura": "Lineup con score completo",
                "conteggio": f"{lineup_coverage['complete_lineups']} / {lineup_coverage['generated_lineups']}",
            },
            {
                "copertura": "Lineup con actual mancanti",
                "conteggio": str(lineup_coverage["incomplete_lineups"]),
            },
        ]
        print_dataframe(
            CONSOLE,
            "Copertura punteggi lineup",
            pd.DataFrame(coverage_rows),
            [("copertura", "Copertura", None), ("conteggio", "Conteggio", None)],
        )
        if not results.empty:
            availability = results.groupby("gameweek", as_index=False).first()
            snapshot_fields = [
                column for column in (
                    "historical_market_available",
                    "historical_coach_market_available",
                    "historical_injuries_available",
                ) if column in availability.columns
            ]
            if snapshot_fields:
                coverage = availability[snapshot_fields].fillna(False).astype(bool).mean()
                coverage_frame = pd.DataFrame(
                    [{
                        "snapshot": column.removeprefix("historical_").replace("_available", ""),
                        "coverage": fraction,
                    } for column, fraction in coverage.items()]
                )
                print_dataframe(
                    CONSOLE,
                    "Copertura snapshot storici",
                    coverage_frame,
                    [("snapshot", "Snapshot", None), ("coverage", "Copertura", ".0%")],
                )
            out = settings.data_path / "backtests" / f"gw{args.from_gw}_{args.to_gw}.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            results.to_parquet(out, index=False)
            CONSOLE.print(f"[bold green]Risultati salvati[/bold green]  {out}")

        selected_strategy = extras.get("selected_holdout_strategy")
        if selected_strategy:
            CONSOLE.print(
                "[bold]Strategia scelta solo sulla validazione[/bold]  "
                f"objective={selected_strategy['objective']}  "
                f"risk_lambda={selected_strategy['risk_lambda']}  "
                f"media team score validazione={selected_strategy['selection_mean_realized_team_score']:.2f}  "
                f"giornate={selected_strategy['selection_gameweeks']}"
            )

        forecast_metrics = extras.get("forecast_metrics", pd.DataFrame())
        if not forecast_metrics.empty:
            print_dataframe(
                CONSOLE,
                f"Qualità predittiva player (holdout finale da GW{extras.get('holdout_start_gameweek')})",
                forecast_metrics,
                [
                    ("gameweek", "GW", "d"),
                    ("evaluation_split", "Split", None),
                    ("n_predictions", "Previsioni", "d"),
                    ("n_player_games", "Campioni", "d"),
                    ("n_missing_actual", "Actual mancanti", "d"),
                    ("actual_coverage", "Copertura actual", ".1%"),
                    ("mae", "MAE", ".2f"),
                    ("rmse", "RMSE", ".2f"),
                    ("bias", "Bias", ".2f"),
                    ("interval_80_coverage", "Copertura P10-P90", ".1%"),
                    ("mean_interval_width", "Ampiezza media", ".2f"),
                ],
            )
            forecast_path = settings.data_path / "backtests" / (
                f"gw{args.from_gw}_{args.to_gw}_forecast_metrics.parquet"
            )
            forecast_path.parent.mkdir(parents=True, exist_ok=True)
            forecast_metrics.to_parquet(forecast_path, index=False)
            CONSOLE.print(f"[dim]Metriche predittive salvate[/dim]  {forecast_path}")

        risk_comparison = extras.get("risk_comparison", pd.DataFrame())
        if not risk_comparison.empty:
            comparison_rows = []
            group_columns = ["objective", "risk_lambda"]
            if "evaluation_split" in risk_comparison.columns:
                group_columns = ["evaluation_split", *group_columns]
            for group_key, group in risk_comparison.groupby(
                group_columns, dropna=False, sort=True
            ):
                if len(group_columns) == 3:
                    evaluation_split, objective, risk_lambda = group_key
                else:
                    objective, risk_lambda = group_key
                    evaluation_split = "all"
                scores = pd.to_numeric(
                    group["realized_player_score"], errors="coerce"
                ).dropna()
                team_scores = pd.to_numeric(
                    group.get("realized_team_score", pd.Series(dtype=float)), errors="coerce"
                ).dropna()
                comparison_rows.append({
                    "evaluation_split": evaluation_split,
                    "objective": objective,
                    "risk_lambda": risk_lambda,
                    "scored_weeks": int(scores.size),
                    "mean_realized_player_score": (
                        float(scores.mean()) if not scores.empty else float("nan")
                    ),
                    "mean_realized_team_score": (
                        float(team_scores.mean()) if not team_scores.empty else float("nan")
                    ),
                })
            print_dataframe(
                CONSOLE,
                "Confronto cronologico expected-value / risk-adjusted",
                pd.DataFrame(comparison_rows),
                [
                    ("evaluation_split", "Split", None),
                    ("objective", "Obiettivo", None),
                    ("risk_lambda", "Lambda", ".2f"),
                    ("scored_weeks", "Settimane valide", "d"),
                    ("mean_realized_player_score", "Player score medio", ".2f"),
                    ("mean_realized_team_score", "Team score medio", ".2f"),
                ],
            )
            risk_path = settings.data_path / "backtests" / (
                f"gw{args.from_gw}_{args.to_gw}_risk_comparison.parquet"
            )
            risk_path.parent.mkdir(parents=True, exist_ok=True)
            risk_comparison.to_parquet(risk_path, index=False)
            CONSOLE.print(f"[bold green]Confronto lambda salvato[/bold green]  {risk_path}")
        else:
            CONSOLE.print(
                "[dim]Confronto del rischio non disponibile: servono risultati giocatore realizzati.[/dim]"
            )

        print_dataframe(
            CONSOLE,
            "Ablation feature",
            extras["ablation"],
            [("variant", "Variante", None), ("player_pdk_mae", "PDK MAE/player-game", ".2f")],
        )
        if not extras["importance"].empty:
            print_dataframe(
                CONSOLE,
                "Importanza feature",
                extras["importance"].head(10),
                [
                    ("feature", "Feature", None),
                    ("category", "Categoria", None),
                    ("importance", "Importanza", ".3f"),
                ],
            )


if __name__ == "__main__":
    main()
