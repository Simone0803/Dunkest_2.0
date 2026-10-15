from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from dunkest.config import Settings
from dunkest.data.http_client import get_json, get_text
from dunkest.rules.pdk import normalize_position

POSITION_MAP = {"1": "G", "2": "F", "3": "C", "G": "G", "F": "F", "C": "C"}
INJURY_TEAM_NAMES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "LA Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


def _injury_status_from_description(description: object) -> str:
    """Translate Dunkest's injury description to a conservative eligibility status."""
    value = " ".join(str(description or "").strip().casefold().split())
    if not value:
        return "UNKNOWN"
    if any(token in value for token in (
        "indisponibile", "fuori per la stagione", "out for the season", "injured reserve", "suspended"
    )) or value == "out" or value.startswith("out "):
        return "OUT"
    if "gtd" in value or "game time decision" in value or "da valutare prima della partita" in value:
        return "GAME TIME DECISION"
    if "doubtful" in value or "in dubbio" in value:
        return "DOUBTFUL"
    if "questionable" in value:
        return "QUESTIONABLE"
    if "probabile" in value or "probable" in value:
        return "PROBABLE"
    if "available" in value or "disponibile" in value:
        return "AVAILABLE"
    return "UNKNOWN"


def _injury_classification(
    description: object, reason: object, injury_date: object, status: str
) -> tuple[str, str, int | None]:
    """Classify the nature/duration of an official injury label conservatively.

    Season-ending is assigned only when Dunkest explicitly says so. Finite
    return dates are treated as estimates; an already-passed date is flagged
    rather than silently interpreting the player as available.
    """
    text = " ".join(str(description or "").casefold().split())
    cause = " ".join(str(reason or "").casefold().split())
    if any(token in text for token in (
        "per tutta la stagione", "fuori per la stagione", "out for the season",
        "season-ending", "season ending",
    )):
        return "SEASON_ENDING", "SEASON_ENDING", None
    if cause in {"riposo", "rest"}:
        return "REST", "REST", None
    if cause in {"nessun infortunio", "no injury"}:
        return "NO_INJURY_REPORTED", "LOW", None

    # The live Italian feed uses labels such as "Indisponibile fino al 2 Gen".
    month_names = {
        "gen": 1, "gennaio": 1, "feb": 2, "febbraio": 2, "mar": 3,
        "marzo": 3, "apr": 4, "aprile": 4, "mag": 5, "maggio": 5,
        "giu": 6, "giugno": 6, "lug": 7, "luglio": 7, "ago": 8,
        "agosto": 8, "set": 9, "sett": 9, "settembre": 9, "ott": 10,
        "ottobre": 10, "nov": 11, "novembre": 11, "dic": 12, "dicembre": 12,
    }
    days: int | None = None
    import re
    match = re.search(r"fino al\s+(\d{1,2})\s+([a-zà-ÿ.]+)", text)
    if match:
        month_token = match.group(2).rstrip(".")
        month = month_names.get(month_token)
        try:
            observed = date.fromisoformat(str(injury_date)[:10])
        except (TypeError, ValueError):
            observed = None
        if month and observed:
            year = observed.year
            try:
                expected = date(year, month, int(match.group(1)))
                # Only roll over into the next calendar year for the Dec -> Jan
                # boundary; other past dates remain explicitly past-dated.
                if expected < observed and (
                    (observed.month == 12 and month == 1)
                    or (observed.month - month) >= 6
                ):
                    expected = date(year + 1, month, int(match.group(1)))
                days = (expected - observed).days
            except ValueError:
                days = None

    if status == "OUT":
        if days is None:
            return "TEMPORARY_OUT", "DURATION_UNKNOWN", None
        if days < 0:
            return "TEMPORARY_OUT", "RETURN_DATE_PASSED", days
        if days <= 14:
            return "TEMPORARY_OUT", "SHORT_TERM", days
        if days <= 45:
            return "TEMPORARY_OUT", "MEDIUM_TERM", days
        return "TEMPORARY_OUT", "LONG_TERM", days
    if status in {"GAME TIME DECISION", "DOUBTFUL", "QUESTIONABLE", "PROBABLE"}:
        return "DAY_TO_DAY", "UNCERTAIN", None
    if cause and cause not in {"sconosciuto", "unknown"}:
        return "INJURY_DURATION_UNKNOWN", "UNKNOWN", None
    return "UNKNOWN", "UNKNOWN", None


def _all_teams_params() -> list[tuple[str, str]]:
    return [("teams[]", str(i)) for i in range(1, 31)]


def _all_positions_params() -> list[tuple[str, str]]:
    return [("positions[]", str(i)) for i in range(1, 4)]


def fetch_week_rounds(settings: Settings, week_number: int) -> list[str]:
    url = f"{settings.dunkest_api_base}/stats/dunkest/week/rounds"
    data = get_json(
        url,
        params={"season_id": settings.season_id, "week_number": week_number},
        timeout=settings.http_timeout,
    )
    return [str(x) for x in data]


def fetch_stats_table(settings: Settings, **table_status: Any) -> pd.DataFrame:
    url = f"{settings.dunkest_api_base}/stats/table"
    params: list[tuple[str, str]] = []
    for key, value in table_status.items():
        if isinstance(value, list):
            for item in value:
                params.append((f"{key}[]", str(item)))
        else:
            params.append((key, str(value)))
    raw = get_json(url, params=params, timeout=settings.http_timeout)
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    if df.empty:
        return df
    df["player_name"] = (df["first_name"].astype(str) + " " + df["last_name"].astype(str)).str.strip()
    df["role"] = df["position_id"].astype(str).map(POSITION_MAP)
    df["role"] = df["role"].fillna(df["position"].apply(normalize_position))
    df["cr"] = pd.to_numeric(df["cr"], errors="coerce").fillna(0.0)
    df["pdk"] = pd.to_numeric(df.get("pdk"), errors="coerce")
    str_cols = {
        "player_name",
        "first_name",
        "last_name",
        "slug",
        "position",
        "role",
        "team_code",
        "team_name",
        "id",
        "team_id",
        "position_id",
    }
    for col in df.columns:
        if col in str_cols:
            df[col] = df[col].astype(str)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_dunkest_gameweek_players(settings: Settings, gameweek: int) -> pd.DataFrame:
    rounds = fetch_week_rounds(settings, gameweek)
    # Dunkest's public stats table is scoped by both gameweek and round.
    # Never guess the round IDs: historical seasons and playoff calendars do
    # not guarantee a fixed number of turns, and invented rounds can return a
    # plausible but incorrect PDK/PLUS sample.
    if not rounds:
        return pd.DataFrame()
    params: dict[str, Any] = {
        "season_id": settings.season_id,
        "mode": "dunkest",
        "stats_type": "avg",
        "weeks": [gameweek],
        "rounds": rounds,
        "teams": [str(i) for i in range(1, 31)],
        "positions": ["1", "2", "3"],
        "min_cr": settings.min_cr,
        "max_cr": settings.max_cr,
        "sort_by": "pdk",
        "sort_order": "desc",
    }
    df = fetch_stats_table(settings, **params)
    if not df.empty:
        df["gameweek"] = gameweek
        # Keep the exact source scope beside the aggregate. This does not
        # claim that the API provides per-NBA-game PDK: it records which
        # Dunkest turns were included in the returned gameweek statistics.
        df["dunkest_rounds"] = ",".join(rounds)
    return df


def fetch_nba_season_players(settings: Settings) -> pd.DataFrame:
    params: dict[str, Any] = {
        "season_id": settings.season_id,
        "mode": "nba",
        "stats_type": "avg",
        "date_from": settings.nba_season_start,
        "date_to": settings.nba_season_end,
        "teams": [str(i) for i in range(1, 31)],
        "positions": ["1", "2", "3"],
        "min_cr": settings.min_cr,
        "max_cr": settings.max_cr,
        "sort_by": "pdk",
        "sort_order": "desc",
    }
    return fetch_stats_table(settings, **params)


def fetch_coach_cr_table(settings: Settings, gameweek: int) -> pd.DataFrame:
    """Coach CR from Dunkest coach stats board (entity=coach when supported)."""
    params: dict[str, Any] = {
        "season_id": settings.season_id,
        "mode": "dunkest",
        "stats_type": "avg",
        "weeks": [gameweek],
        "teams": [str(i) for i in range(1, 31)],
        "entity": "coach",
        "min_cr": 1,
        "max_cr": settings.max_cr,
    }
    df = fetch_stats_table(settings, **params)
    if df.empty or "position" in df.columns and df["position"].iloc[0] in ("G", "F", "C"):
        # API returned players — use NBA mode coach-like rows not available; build from config later
        return pd.DataFrame()
    return df


def _parse_fantasy_injuries_payload(payload: object) -> pd.DataFrame:
    """Parse the official Flutter API response captured from /1/injuries."""
    if not isinstance(payload, dict):
        raise RuntimeError("Risposta API infortuni Dunkest non valida: atteso un oggetto JSON.")
    data = payload.get("data")
    players = data.get("players") if isinstance(data, dict) else None
    if not isinstance(players, list):
        raise RuntimeError(
            "Risposta API infortuni Dunkest incompleta: manca data.players; "
            "non uso la pagina web legacy come sostituto."
        )

    rows: list[dict[str, object]] = []
    for player in players:
        if not isinstance(player, dict):
            continue
        injury = player.get("injury")
        if not isinstance(injury, dict):
            continue
        first_name = str(player.get("first_name") or "").strip()
        last_name = str(player.get("last_name") or "").strip()
        player_name = " ".join(part for part in (first_name, last_name) if part)
        team_info = player.get("team")
        team = (
            str(team_info.get("abbreviation") or team_info.get("code") or "").strip().upper()
            if isinstance(team_info, dict)
            else ""
        )
        description = str(injury.get("description") or "").strip()
        reason = str(injury.get("reason") or "").strip()
        reported_date = str(injury.get("date") or "").strip()
        if not player_name or not team or not description:
            continue
        status = _injury_status_from_description(description)
        injury_type, severity, expected_return_days = _injury_classification(
            description, reason, reported_date, status
        )
        rows.append({
            "player_name": player_name,
            "status": status,
            "team": team,
            "injury_reason": reason,
            "injury_date": reported_date,
            "injury_description": description,
            "injury_type": injury_type,
            "injury_severity": severity,
            "expected_return_days": expected_return_days,
            "season_ending": injury_type == "SEASON_ENDING",
            "source_url": "https://fantasy.dunkest.com/1/injuries",
        })

    result = pd.DataFrame(rows)
    if result.empty:
        raise RuntimeError(
            "L'API ufficiale Dunkest ha risposto ma non ha restituito giocatori "
            "con stato infortuni leggibile; interrompo per evitare rose non sicure."
        )
    return result.drop_duplicates(["player_name", "team"], keep="last").reset_index(drop=True)


def _fetch_fantasy_injuries_payload(settings: Settings) -> dict[str, Any]:
    """Open the official Flutter injury route and capture its own API response.

    It deliberately shares Lineups' private persistent Chromium profile and
    Flutter accessibility bootstrap. Credentials are never read or logged.
    """
    from dunkest.data.dunkest.lineups_browser import (
        _enable_flutter_accessibility,
        _lineups_browser_profile_dir,
    )

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright è necessario per leggere gli infortuni ufficiali: "
            "installa Playwright e Chromium nell'ambiente del progetto."
        ) from exc

    target_url = "https://fantasy.dunkest.com/1/injuries"
    captured: dict[str, Any] = {}
    with sync_playwright() as playwright:
        profile_dir = _lineups_browser_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            profile_dir.chmod(0o700)
        except OSError:
            pass
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                viewport={"width": 1680, "height": 1000},
            )
        except PlaywrightError as exc:
            raise RuntimeError(
                "Non riesco ad aprire il profilo Chromium persistente per gli infortuni. "
                "Chiudi eventuali finestre Chromium avviate dallo scraper e riprova."
            ) from exc

        page = context.new_page()

        def capture(response) -> None:
            # Capture only the documented injury endpoint; never log request
            # headers, cookies, tokens, or unrelated authenticated responses.
            if "/api/v1/leagues/1/injuries" not in response.url.split("?", 1)[0]:
                return
            captured["status"] = int(response.status)
            try:
                captured["payload"] = response.json()
            except Exception:
                captured["payload"] = None

        page.on("response", capture)
        try:
            page.goto(
                target_url,
                wait_until="domcontentloaded",
                timeout=max(1000, int(settings.http_timeout * 1000)),
            )
            page.wait_for_timeout(1000)
            _enable_flutter_accessibility(page)
            # Scroll the rendered injuries view all the way down: Flutter may
            # lazy-render the list and/or request its data only after scrolling.
            page.mouse.move(0.5 * page.viewport_size["width"], 0.75 * page.viewport_size["height"])
            stagnant = 0
            for _ in range(70):
                before = page.evaluate("""() => {
                  const root = document.scrollingElement;
                  const scrollables = [...document.querySelectorAll('*')].filter(el =>
                    el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 8 &&
                    getComputedStyle(el).visibility !== 'hidden');
                  return JSON.stringify([root ? root.scrollTop : 0, ...scrollables.map(el =>
                    [Math.round(el.scrollTop), el.scrollHeight - el.clientHeight])]);
                }""")
                page.mouse.wheel(0, 900)
                page.keyboard.press("PageDown")
                # Nudge scrollable Flutter/DOM containers as well as the viewport.
                page.evaluate("""() => {
                  const root = document.scrollingElement;
                  if (root) root.scrollTop = Math.min(root.scrollHeight, root.scrollTop + Math.max(400, root.clientHeight * 0.8));
                  const els = [...document.querySelectorAll('*')].filter(el =>
                    el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 8 &&
                    getComputedStyle(el).visibility !== 'hidden');
                  for (const el of els) el.scrollTop = Math.min(el.scrollHeight, el.scrollTop + Math.max(350, el.clientHeight * 0.8));
                }""")
                page.wait_for_timeout(160)
                after = page.evaluate("""() => {
                  const root = document.scrollingElement;
                  const scrollables = [...document.querySelectorAll('*')].filter(el =>
                    el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 8 &&
                    getComputedStyle(el).visibility !== 'hidden');
                  return JSON.stringify([root ? root.scrollTop : 0, ...scrollables.map(el =>
                    [Math.round(el.scrollTop), el.scrollHeight - el.clientHeight])]);
                }""")
                if before == after:
                    stagnant += 1
                    if stagnant >= 3:
                        break
                else:
                    stagnant = 0
            page.keyboard.press("End")
            page.evaluate("""() => {
              if (document.scrollingElement) document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
              for (const el of document.querySelectorAll('*'))
                if (el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 8) el.scrollTop = el.scrollHeight;
            }""")
            page.wait_for_timeout(1800)
            # The app loads the injuries endpoint asynchronously after the
            # Flutter shell and semantics layer initialize; scroll can trigger it.
            if "payload" not in captured:
                page.wait_for_timeout(3000)
        except Exception as exc:
            context.close()
            raise RuntimeError(
                "Impossibile caricare la pagina ufficiale Fantasy Dunkest /1/injuries."
            ) from exc
        finally:
            try:
                context.close()
            except Exception:
                pass

    if captured.get("status") != 200 or not isinstance(captured.get("payload"), dict):
        raise RuntimeError(
            "La pagina /1/injuries non ha restituito una risposta valida "
            "dall'endpoint ufficiale /api/v1/leagues/1/injuries."
        )
    return captured["payload"]


def scrape_injuries(settings: Settings) -> pd.DataFrame:
    """Scrape availability from the official Fantasy Dunkest Flutter app.

    No legacy-site fallback is allowed: an incomplete official capture must
    fail closed instead of silently dropping injuries from the player pool.
    """
    payload = _fetch_fantasy_injuries_payload(settings)
    return _parse_fantasy_injuries_payload(payload)
