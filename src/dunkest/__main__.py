from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dunkest.backtest.walk_forward import run_walk_forward_backtest
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="dunkest")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="Fetch and cache data")
    p_collect.add_argument("--season", default=None)
    p_collect.add_argument("--force", action="store_true")

    p_run = sub.add_parser("run", help="Predict and optimize next gameweek")
    p_run.add_argument("--giornata", type=int, required=True)
    p_run.add_argument("--turno", type=int, default=None, help="Turno Dunkest separato dalla Giornata; richiesto quando si esegue lo scraping Lineups")
    p_run.add_argument("--budget", type=float, default=None)
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
    p_open.add_argument("--turno", type=int, default=None, help="Turno Dunkest da leggere nello scraper Lineups")
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
        settings.target_dunkest_turn = args.turno
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
                if args.turno is None:
                    parser.error("specifica --turno: il Turno Dunkest non viene dedotto dalla Giornata")
                try:
                    from dunkest.data.dunkest.lineups_browser import scrape_lineups_market

                    scrape_lineups_market(credits_file, turn_number=args.turno)
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
        out = save_run_artifacts(settings, preds, solutions, None)
        market.to_parquet(out / "opening_market.parquet", index=False)
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
        settings.target_dunkest_turn = args.turno
        if args.budget is not None:
            settings.budget = args.budget
        if args.giornata > 1 and not args.roster:
            parser.error("dalla giornata 2 devi indicare --roster con i 10 giocatori e il coach attuali")
        if args.roster:
            players, coach = load_roster_yaml(args.roster)
            if args.giornata > 1:
                if len(players) != 10 or coach is None:
                    parser.error("il file --roster deve contenere esattamente 10 giocatori e un coach")
                normalized = [str(p).strip().casefold() for p in players]
                if any(not name for name in normalized) or len(set(normalized)) != 10:
                    parser.error("la rosa attuale contiene nomi vuoti o giocatori duplicati")
            settings.current_roster = players
            settings.current_coach = coach
        if not args.no_lineups_scrape:
            if args.turno is None:
                parser.error("specifica --turno: il Turno Dunkest non viene dedotto dalla Giornata")
            try:
                from dunkest.data.dunkest.lineups_browser import scrape_lineups_market

                scrape_lineups_market(
                    settings.data_path / "current_lineups_market.csv",
                    turn_number=args.turno,
                )
            except Exception as exc:
                parser.error(f"Scraping Lineups non riuscito: {exc}")
        if args.giornata > 1:
            settings.transfer_penalty = 5.0 if args.transfer_penalty is None else args.transfer_penalty
        elif args.transfer_penalty is not None:
            settings.transfer_penalty = args.transfer_penalty
        models, features = run_train(settings)
        preds, coach_df = run_predict(settings, models, features)
        try:
            solutions = run_optimize(settings, preds, coach_df)
        except ValueError as exc:
            parser.error(str(exc))
        for i, sol in enumerate(solutions, start=1):
            sol.rank = i
        print_matchday_report(settings, preds, coach_df, solutions)
        out = save_run_artifacts(settings, preds, solutions, models)
        CONSOLE.print(f"\n[bold green]Artefatti salvati[/bold green]  {out}")
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
            return
        metrics = pd.DataFrame(
            [
                {"metric": "Player score medio", "value": report.average_player_score},
                {"metric": "Player score mediano", "value": report.median_player_score},
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
                    ("n_player_games", "Campioni", "d"),
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
