from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_PROJECT_ROOT = Path(__file__).resolve().parents[4]

from dunkest.names import player_key, player_surname


API_HOST = "fantaking-api.dunkest.com/api/v1/"
LINEUPS_PATH = re.compile(r"/matches/\d+/lineups/?$")
TEAM_CODES = {
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
}
POSITION_MAP = {
    "1": "G", "guard": "G", "g": "G", "point guard": "G", "shooting guard": "G",
    "2": "A", "forward": "A", "f": "A", "a": "A", "small forward": "A", "power forward": "A",
    "3": "C", "center": "C", "centre": "C", "c": "C",
}
UI_ROLE_MAP = {"G": "G", "A": "A", "F": "A", "C": "C", "HC": "HC"}


def _lineups_browser_profile_dir() -> Path:
    """Return the private, persistent Chromium profile used for Dunkest login."""
    configured = os.environ.get("DUNKEST_LINEUPS_PROFILE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".dunkest-optimizer" / "lineups-browser-profile"


def _parse_lineup_label(label: str, team: str, lineup_group: str) -> dict[str, Any] | None:
    """Parse Flutter's accessible label, e.g. 'G CURRY 15cr 0'."""
    text = " ".join(str(label).replace(",", ".").split()).strip()
    # The unavailable panel occasionally exposes accessibility/advertising
    # copy as if it were a player label. This includes English accessibility
    # text and Dutch promotional fragments visible on the live Dunkest page.
    # Reject exact normalized UI strings before surname matching so they can
    # never be treated as injury labels or exclude a real player.
    unavailable_ui_noise = {
        "learn more",
        "path to success",
        "nu samenstellen",
        "ijzersterke",
        "hapert samen",
        "stel nu jouw",
        "bekijk je premie",
        "hire an expert",
    }
    if lineup_group == "INDISPONIBILI" and player_key(text) in unavailable_ui_noise:
        return None
    if (
        re.search(r"\b(?:ADVERTISEMENT|ADVERTISING|LEGENDA|PUNTEGGI|INDISPONIBILI)\b", text, re.I)
        or re.search(r"\b\d{1,2}/\d{1,2}\b", text)
        # Flutter/advertising semantics sometimes produce fragments such as
        # "quaintance *". Never resolve a decorative star/bullet as a surname.
        or (lineup_group == "INDISPONIBILI" and re.search(r"[*★☆•▪■]", text))
    ):
        return None
    role_match = re.search(r"(?:^|\s)(HC|G|A|F|C)(?:\s|$)", text, re.I)
    if not role_match and lineup_group != "INDISPONIBILI":
        return None
    role = UI_ROLE_MAP[role_match.group(1).upper()] if role_match else "ANY"
    cr_match = re.search(r"(\d+(?:\.\d+)?)\s*cr\b", text, re.I)
    cr = float(cr_match.group(1)) if cr_match else None
    name = text
    if cr_match:
        name = name[:cr_match.start()] + " " + name[cr_match.end():]
    name = re.sub(r"(?:^|\s)-?\d+(?:\.\d+)?$", "", name).strip()
    name = re.sub(r"\b(?:HC|G|A|F|C)\b", " ", name, flags=re.I)
    if role == "ANY":
        name = re.sub(r"\b(?:OUT|INDISPONIBILE|INDISPONIBILI|INJURED|UNAVAILABLE)\b", " ", name, flags=re.I)
    name = " ".join(name.split())
    # Flutter OCR sometimes appends copyright/trademark/equality glyphs to
    # surnames in the league-wide injury panel (e.g. "Hukporti ©", "Miller =").
    name = re.sub(r"[\s©®™=«»]+$", "", name).strip(" -")
    if not name:
        return None
    # Lineups accessibility labels normally expose surnames only; canonical
    # names are resolved against the full list returned by the API/snapshot.
    return {
        "surname": name.casefold().split()[-1],
        "ui_name": name.casefold(),
        "team": team,
        "role": role,
        "cr": cr,
        "lineup_group": lineup_group,
    }


def _collect_lineup_annotations_state(
    page, fixture_label: str, *, unavailable_section_active: bool = False
) -> tuple[list[dict[str, Any]], bool]:
    """Read visible labels; never guess that unclassified text is unavailable.

    Flutter virtualizes this long page. Carry an observed INDISPONIBILI heading
    across scroll steps, but ignore bare names until that heading is seen.
    """
    match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
    if not match:
        return [], unavailable_section_active
    home, away = match.group(1).upper(), match.group(2).upper()
    nodes = page.evaluate("""() => {
      const roots = [document], out = [];
      while (roots.length) {
        const root = roots.pop();
        for (const el of root.querySelectorAll('*')) {
          if (el.shadowRoot) roots.push(el.shadowRoot);
          const label = (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim();
          if (!label || label.length > 100) continue;
          const r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0 || r.bottom <= 0 || r.top >= window.innerHeight
              || r.right <= 0 || r.left >= window.innerWidth) continue;
          const lineupText = /\\b(?:HC|G|A|F|C)\\b/i.test(label);
          const sectionText = /\\b(?:QUINTETTO|PANCHINA|INDISPONIBILI)\\b/i.test(label);
          const nameText = /^[A-Z][A-Za-z'. -]{1,40}$/.test(label);
          // Dunkest marks lineup rows as progressbars, but the injury panel
          // can be plain Flutter text without aria-label or an explicit role.
          if (el.hasAttribute('aria-label') || el.getAttribute('role') === 'progressbar'
              || lineupText || sectionText || nameText) {
            out.push({label, x: r.left + r.width / 2, y: r.top + r.height / 2});
          }
        }
      }
      return {width: window.innerWidth, nodes: out};
    }""")
    width = float(nodes.get("width") or 0)
    raw_items = nodes.get("nodes") or []
    items = []
    seen_items: set[tuple[str, int, int]] = set()
    for node in raw_items:
        signature = (
            str(node.get("label", "")),
            round(float(node.get("x", 0)) / 4),
            round(float(node.get("y", 0)) / 4),
        )
        if signature not in seen_items:
            seen_items.add(signature)
            items.append(node)
    # Infer the two lineup columns from player-row coordinates rather than
    # splitting at the browser midpoint. Flutter's content can be narrower than
    # the viewport, putting both column headings left of window.innerWidth / 2.
    player_x = sorted(
        float(node.get("x", 0))
        for node in items
        if re.search(r"(?:^|\s)(?:HC|G|A|F|C)(?:\s|$)", str(node.get("label", "")), re.I)
        and re.search(r"\d+(?:[,.]\d+)?\s*cr\b", str(node.get("label", "")), re.I)
    )
    column_threshold = width / 2
    if len(player_x) >= 8:
        gaps = [(player_x[index + 1] - player_x[index], index) for index in range(len(player_x) - 1)]
        gap, split_index = max(gaps, default=(0.0, 0))
        if gap >= max(80.0, width * 0.06):
            column_threshold = (player_x[split_index] + player_x[split_index + 1]) / 2

    # Treat the score legend as an explicit end marker for the unavailable
    # panel. Carry its context only while scrolling inside the panel; otherwise
    # plain advertising/related-content text below it can be misread as a player.
    markers = []
    for node in items:
        label = " ".join(str(node.get("label", "")).upper().split())
        y = float(node.get("y", 0))
        section_heading = re.search(r"\b(QUINTETTO|PANCHINA|INDISPONIBILI)\b", label)
        if section_heading:
            section = section_heading.group(1)
            # Starter/bench headings belong to one team column. The unavailable
            # panel and its legend span the whole card and remain global.
            marker_team = None if section == "INDISPONIBILI" else (
                home if float(node.get("x", 0)) < column_threshold else away
            )
            markers.append((y, marker_team, section))
        elif re.search(r"\b(?:LEGENDA|PUNTEGGI)\b", label):
            markers.append((y, None, "END_INDISPONIBILI"))
    markers.sort(key=lambda item: item[0])

    annotations: list[dict[str, Any]] = []
    starter_count = {home: 0, away: 0}
    section_active = unavailable_section_active
    for node in sorted(items, key=lambda item: float(item.get("y", 0))):
        label = str(node.get("label", ""))
        y = float(node.get("y", 0))
        team = home if float(node.get("x", 0)) < column_threshold else away
        legend_reached = any(
            top <= y + 2 and marker == "END_INDISPONIBILI"
            for top, _, marker in markers
        )
        if legend_reached:
            section = "AFTER_INDISPONIBILI"
            section_active = False
        else:
            prior_markers = [
                marker for top, marker_team, marker in markers
                if top <= y + 2 and (marker_team is None or marker_team == team)
            ]
            if prior_markers:
                marker = prior_markers[-1]
                if marker == "INDISPONIBILI":
                    section = "INDISPONIBILI"
                    section_active = True
                    if re.search(r"\bHC\b", label, re.I):
                        continue
                else:
                    section = marker
            else:
                if re.search(r"\bHC\b", label, re.I):
                    section = "COACH"
                elif re.search(r"\d+(?:[,.]\d+)?\s*cr\b", label, re.I):
                    section = "QUINTETTO" if starter_count[team] < 5 else "PANCHINA"
                elif section_active:
                    section = "INDISPONIBILI"
                else:
                    continue
        if section == "AFTER_INDISPONIBILI":
            continue
        if re.fullmatch(r"\s*(?:QUINTETTO|PANCHINA|INDISPONIBILI)(?:\s*\(\d+\))?\s*", label, re.I):
            if re.match(r"\s*QUINTETTO\b", label, re.I):
                starter_count[team] = 0
            continue
        # A missing/mispositioned bench heading must not turn an entire roster
        # into starters. Reset at each visible starting-five heading, then cap
        # that fixture's starter labels at five per team column.
        is_player_row = (
            re.search(r"(?:^|\s)(?:G|A|F|C)(?:\s|$)", label, re.I)
            and re.search(r"\d+(?:[,.]\d+)?\s*cr\b", label, re.I)
        )
        if section == "QUINTETTO" and is_player_row:
            if starter_count[team] >= 5:
                section = "PANCHINA"
            else:
                starter_count[team] += 1
        parsed = _parse_lineup_label(label, team, section)
        if parsed:
            annotations.append(parsed)
    deduplicated = {}
    for annotation in annotations:
        key = (annotation["team"], annotation["surname"], annotation["lineup_group"])
        previous = deduplicated.get(key)
        if previous is None or (previous["role"] == "ANY" and annotation["role"] != "ANY"):
            deduplicated[key] = annotation
    return list(deduplicated.values()), section_active


def _collect_lineup_annotations(page, fixture_label: str) -> list[dict[str, Any]]:
    annotations, _ = _collect_lineup_annotations_state(page, fixture_label)
    return annotations


def _annotations_from_ocr_tsv(tsv: str) -> tuple[list[dict[str, Any]], bool]:
    """Read only player names between the visible OUT heading and score legend."""
    rows = list(csv.DictReader(io.StringIO(tsv), delimiter="\t"))
    page_width = 0.0
    for row in rows:
        if row.get("level") == "1":
            page_width = float(row.get("width") or 0)
            break
    if not page_width:
        return [], False
    lines: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        try:
            left = float(row.get("left") or 0)
            top = float(row.get("top") or 0)
            confidence = float(row.get("conf") or -1)
        except (TypeError, ValueError):
            continue
        # The left sidebar contains unrelated navigation labels. The player
        # cards are centered/right in the Lineups content area.
        if left < page_width * 0.32 or confidence < 10:
            continue
        key = (row.get("block_num", ""), row.get("par_num", ""), row.get("line_num", ""))
        lines.setdefault(key, []).append({"text": row["text"].strip(), "top": top, "left": left})
    ordered = sorted(
        ((min(word["top"] for word in words), words) for words in lines.values()),
        key=lambda item: item[0],
    )
    heading_index = next(
        (i for i, (_, words) in enumerate(ordered)
         if re.search(r"\bINDISPONIBILI\b", " ".join(w["text"] for w in words), re.I)),
        None,
    )
    if heading_index is None:
        return [], False
    annotations: list[dict[str, Any]] = []
    for _, words in ordered[heading_index + 1:]:
        label = " ".join(word["text"] for word in sorted(words, key=lambda w: w["left"]))
        if re.search(r"\bLEGENDA\b", label, re.I):
            break
        normalized = re.sub(r"[^A-ZÀ-ÖØ-Þ0-9'. -]", " ", label.upper())
        normalized = " ".join(normalized.split())
        # A row needs an actual name token; isolated position badges or
        # numbers are not evidence that a player is unavailable.
        name = re.sub(r"\b(?:HC|G|A|F|C|OUT)\b", " ", normalized, flags=re.I)
        name = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:CR)?\b", " ", name, flags=re.I)
        name = " ".join(name.split()).strip(" -.")
        if not re.search(r"[A-Z]{3,}", name):
            continue
        parsed = _parse_lineup_label(label, "", "INDISPONIBILI")
        if parsed is not None:
            annotations.append(parsed)
    return annotations, True


def _ocr_unavailable_panel(page) -> tuple[list[dict[str, Any]], bool]:
    """Fallback for Flutter builds that expose the canvas visually but not semantically."""
    executable = shutil.which("tesseract")
    if not executable:
        return [], False
    try:
        image_bytes = page.screenshot(full_page=False)
        result = subprocess.run(
            [executable, "stdin", "stdout", "tsv"], input=image_bytes,
            capture_output=True, check=False, timeout=12,
        )
        if result.returncode != 0:
            return [], False
        return _annotations_from_ocr_tsv(result.stdout.decode("utf-8", errors="replace"))
    except Exception:
        return [], False


def _cap_fixture_lineup_annotations(
    annotations: list[dict[str, Any]], fixture_teams: set[str]
) -> list[dict[str, Any]]:
    """Cap starter labels per team for one fixture after all scroll passes.

    The Flutter accessibility tree can be observed repeatedly while scrolling;
    a fresh five-player counter on every viewport otherwise promotes additional
    bench players to starters. Apply the cap only after merging the whole
    fixture's observations, not across the complete gameweek.
    """
    rows = [dict(item) for item in annotations]
    def player_identity(item: dict[str, Any]) -> tuple[str, str, str]:
        surname = player_key(item.get("surname") or item.get("ui_name"))
        role = str(item.get("role", "")).strip().upper()
        try:
            price = f"{float(item.get('cr')):.2f}"
        except (TypeError, ValueError):
            price = ""
        return surname, role, price

    # Surnames alone are not player identities (e.g. two Williams on one team).
    # Use role + displayed CR to distinguish them before enforcing five starters.
    selected_starters: dict[str, set[tuple[str, str, str]]] = {team: set() for team in fixture_teams}
    for team in fixture_teams:
        for item in rows:
            if str(item.get("team", "")).upper() != team:
                continue
            if str(item.get("lineup_group", "")).upper() != "QUINTETTO":
                continue
            if str(item.get("role", "")).upper() == "HC":
                continue
            identity = player_identity(item)
            if identity[0] and (identity in selected_starters[team] or len(selected_starters[team]) < 5):
                selected_starters[team].add(identity)

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    for item in rows:
        team = str(item.get("team", "")).upper()
        group = str(item.get("lineup_group", "")).upper()
        identity = player_identity(item)
        if team in selected_starters and group == "QUINTETTO" and identity not in selected_starters[team]:
            item["lineup_group"] = "PANCHINA"
            group = "PANCHINA"
        elif team in selected_starters and group == "PANCHINA" and identity in selected_starters[team]:
            continue
        surname = identity[0]
        scope = tuple(item.get("_fixture_teams", ()))
        key = (
            team, str(item.get("role", "")), surname, group, scope,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _scroll_collect_lineup_annotations(page, fixture_label: str, *, max_steps: int = 60) -> list[dict[str, Any]]:
    """Scroll a fixture and collect only roster/coach labels, never injury labels."""
    found: dict[tuple[Any, ...], dict[str, Any]] = {}
    stalled = 0
    unavailable_section_active = False
    fixture_match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
    fixture_teams = (
        {fixture_match.group(1).upper(), fixture_match.group(2).upper()}
        if fixture_match else set()
    )

    def add_annotations(annotations: list[dict[str, Any]]) -> None:
        for annotation in annotations:
            item = dict(annotation)
            group = str(item.get("lineup_group", "")).upper()
            # Injury/unavailable labels belong to the separate /injuries scrape.
            # They often omit team identity and must never contaminate the market.
            if group == "INDISPONIBILI":
                continue
            if fixture_teams and str(item.get("team", "")).upper() not in fixture_teams:
                continue
            if fixture_teams:
                item["_fixture_teams"] = tuple(sorted(fixture_teams))
            fixture_scope = tuple(item.get("_fixture_teams", ()))
            key = (
                str(item.get("team", "")), str(item.get("role", "")),
                str(item.get("surname", "")), group, fixture_scope,
            )
            found[key] = item

    page.mouse.move(0.5 * page.viewport_size["width"], 0.8 * page.viewport_size["height"])
    for _ in range(max_steps):
        # Collect before scrolling as the first lineup rows can be above the
        # fold. Scroll via real wheel/PageDown events so Flutter's own vertical
        # scroll controller receives the input; do not move unrelated panes.
        annotations, unavailable_section_active = _collect_lineup_annotations_state(
            page, fixture_label, unavailable_section_active=unavailable_section_active
        )
        add_annotations(annotations)
        before = _vertical_scroll_snapshot(page)
        page.mouse.wheel(0, 680)
        page.wait_for_timeout(180)
        after = _vertical_scroll_snapshot(page)
        if after == before:
            page.keyboard.press("PageDown")
            page.wait_for_timeout(180)
            after = _vertical_scroll_snapshot(page)
        annotations, unavailable_section_active = _collect_lineup_annotations_state(
            page, fixture_label, unavailable_section_active=unavailable_section_active
        )
        add_annotations(annotations)
        if after != before:
            stalled = 0
        else:
            stalled += 1
            if stalled >= 3:
                page.keyboard.press("End")
                page.wait_for_timeout(180)
                annotations, unavailable_section_active = _collect_lineup_annotations_state(
                    page, fixture_label, unavailable_section_active=unavailable_section_active
                )
                add_annotations(annotations)
                break
    # Return the document viewport to the schedule without resetting carousel
    # offsets or hidden nested views. Injury labels are intentionally not read here.
    page.keyboard.press("Home")
    page.mouse.wheel(0, -12000)
    page.wait_for_timeout(180)
    return _cap_fixture_lineup_annotations(list(found.values()), fixture_teams)


def _vertical_scroll_snapshot(page) -> tuple[tuple[int, int, int], ...]:
    """Read top-level vertical scroll positions to detect real page movement."""
    try:
        values = page.evaluate("""() => {
          const roots = [document], pending = [document], elements = [];
          while (pending.length) {
            const root = pending.pop();
            for (const el of root.querySelectorAll('*')) {
              elements.push(el);
              if (el.shadowRoot) pending.push(el.shadowRoot);
            }
          }
          elements.push(document.scrollingElement);
          return elements.filter(el => el && el.scrollHeight > el.clientHeight + 8)
            .map(el => [el.scrollHeight - el.clientHeight, el.clientHeight, el.scrollTop]);
        }""")
        return tuple(tuple(round(float(value)) for value in row) for row in values)
    except Exception:
        return ()


def _fixtures_from_accessibility_nodes(nodes: list[dict[str, Any]], turn_number: int) -> list[str]:
    """Associate Lineups fixture buttons with the nearest TURNO heading."""
    entries = []
    seen = set()
    for item in nodes:
        label = " ".join(str(item.get("label", "")).split())
        y = float(item.get("y", 0))
        key = (label, round(y / 4))
        if key not in seen:
            seen.add(key)
            entries.append((y, label))
    entries.sort()
    active_week = None
    fixtures: list[str] = []
    for _, label in entries:
        week = re.search(r"\bTURNO\s+(\d+)\b", label, re.I)
        if week:
            active_week = int(week.group(1))
        if active_week == turn_number and re.search(r"\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b", label, re.I):
            if label not in fixtures:
                fixtures.append(label)
    return fixtures


def _fixture_observation(
    fixture_label: str,
    turn_number: int | None,
    observed_at_utc: str,
    team_eligibility: dict[str, bool | None] | None = None,
) -> dict[str, Any] | None:
    """Normalize a Dunkest fixture label into a compact, auditable record."""
    match = re.search(
        r"(?:(?:TURNO\s+\d+)\s+)?(\d{1,2})/(\d{1,2})\s+([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b",
        " ".join(str(fixture_label).upper().split()),
    )
    if not match:
        return None
    team_a, team_b = match.group(3), match.group(4)
    eligibility = team_eligibility or {}
    status_key = _fixture_status_key(fixture_label)
    keyed_eligibility = eligibility.get(status_key) or eligibility.get(
        _fixture_pair_key(fixture_label), eligibility
    )
    return {
        "fixture_label": " ".join(str(fixture_label).split()),
        "team_a": team_a,
        "team_b": team_b,
        "team_a_eligible": keyed_eligibility.get(team_a),
        "team_b_eligible": keyed_eligibility.get(team_b),
        "display_day": match.group(1),
        "display_month": match.group(2),
        "dunkest_turn": int(turn_number) if turn_number is not None else None,
        "observed_at_utc": str(observed_at_utc),
    }


def _eligibility_flag(value: object) -> bool | None:
    if value is True or str(value).strip().casefold() in {"true", "1", "yes"}:
        return True
    if value is False or str(value).strip().casefold() in {"false", "0", "no"}:
        return False
    return None


def _eligible_teams_from_fixture_rows(rows: list[dict[str, Any]]) -> set[str]:
    teams: set[str] = set()
    for row in rows:
        for team_col, eligible_col in (
            ("team_a", "team_a_eligible"),
            ("team_b", "team_b_eligible"),
        ):
            team = str(row.get(team_col, "")).strip().upper()
            if team and _eligibility_flag(row.get(eligible_col)) is True:
                teams.add(team)
    return teams


def _retain_previous_verified_fixture_eligibility(
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Avoid replacing complete fixture coverage with a weaker browser observation.

    The UI's black/gray side styling can occasionally be misread. If the same
    schedule previously had all 30 teams eligible but the latest observation
    leaves a team with no eligible fixture, retain the prior positive side flag
    for that team and record the conflict. Never infer eligibility for a team
    without a previous positive observation.
    """
    rows = [dict(row) for row in current_rows]
    if not rows or not previous_rows:
        return rows, []
    def signature(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(row.get("team_a", "")).strip().upper(),
            str(row.get("team_b", "")).strip().upper(),
            str(row.get("display_day", "")).strip(),
            str(row.get("display_month", "")).strip(),
            str(row.get("dunkest_turn", "")).strip(),
        )
    if {signature(row) for row in rows} != {signature(row) for row in previous_rows}:
        return rows, []
    previous_eligible = _eligible_teams_from_fixture_rows(previous_rows)
    current_eligible = _eligible_teams_from_fixture_rows(rows)
    if len(previous_eligible) < 30 or len(current_eligible) >= len(previous_eligible):
        return rows, []
    previous_by_signature = {signature(row): row for row in previous_rows}
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        prior = previous_by_signature.get(signature(row), {})
        for team_col, eligible_col in (
            ("team_a", "team_a_eligible"),
            ("team_b", "team_b_eligible"),
        ):
            team = str(row.get(team_col, "")).strip().upper()
            current_flag = _eligibility_flag(row.get(eligible_col))
            previous_flag = _eligibility_flag(prior.get(eligible_col))
            if team and team not in current_eligible and current_flag is not True and previous_flag is True:
                row[eligible_col] = True
                current_eligible.add(team)
                conflicts.append({
                    "fixture_label": str(row.get("fixture_label", "")),
                    "team": team,
                    "observed_eligible": current_flag,
                    "retained_previous_eligible": True,
                })
    return rows, conflicts


def _fixture_status_key(label: str) -> str:
    match = re.search(
        r"(?:(\d{1,2})/(\d{1,2})\s+)?([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b",
        " ".join(str(label).upper().split()),
    )
    if not match:
        return " ".join(str(label).upper().split())
    day, month, first, second = match.groups()
    return f"{day or ''}/{month or ''}|{first}|{second}"


def _fixture_pair_key(label: str) -> str:
    match = re.search(
        r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b",
        " ".join(str(label).upper().split()),
    )
    return f"pair|{match.group(1)}|{match.group(2)}" if match else ""


def _all_fixtures_from_accessibility_nodes(nodes: list[dict[str, Any]]) -> list[str]:
    fixtures: list[str] = []
    for item in nodes:
        label = " ".join(str(item.get("label", "")).split())
        if re.search(r"\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b", label, re.I) and label not in fixtures:
            fixtures.append(label)
    return fixtures


def _teams_in_fixtures(labels: list[str]) -> set[str]:
    """Teams whose current prices/coaches are required by the visible schedule."""
    teams: set[str] = set()
    for label in labels:
        match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", label, re.I)
        if match:
            teams.update((match.group(1).upper(), match.group(2).upper()))
    return teams


def _fixture_labels_from_batches(
    batches: list[list[dict[str, Any]]], turn_number: int | None
) -> tuple[list[str], list[str]]:
    """Merge fixture controls exposed as a long, lazily-rendered scroll list."""
    all_fixtures: list[str] = []
    target_fixtures: list[str] = []
    active_week: int | None = None
    for batch in batches:
        ordered = sorted(batch, key=lambda item: float(item.get("y", 0)))
        for item in ordered:
            label = " ".join(str(item.get("label", "")).split())
            week = re.search(r"\bTURNO\s+(\d+)\b", label, re.I)
            if week:
                active_week = int(week.group(1))
            if not re.search(r"\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b", label, re.I):
                continue
            if label not in all_fixtures:
                all_fixtures.append(label)
            if (turn_number is None or active_week == turn_number) and label not in target_fixtures:
                target_fixtures.append(label)
    return all_fixtures, target_fixtures


def _fixture_turn_map_from_batches(batches: list[list[dict[str, Any]]]) -> dict[str, int]:
    """Keep the TURNO heading attached to every lazily loaded fixture card."""
    result: dict[str, int] = {}
    active_turn: int | None = None
    for batch in batches:
        for item in sorted(batch, key=lambda value: float(value.get("y", 0))):
            label = " ".join(str(item.get("label", "")).split())
            heading = re.search(r"\bTURNO\s+(\d+)\b", label, re.I)
            if heading:
                active_turn = int(heading.group(1))
            if active_turn is not None and re.search(
                r"\b\d{1,2}/\d{1,2}\s+[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b", label, re.I
            ):
                result[label] = active_turn
    return result


def _fixture_labels_for_turn(page, turn_number: int) -> list[str]:
    return _fixtures_from_accessibility_nodes(_fixture_nodes(page), turn_number)


def _all_fixture_labels(page) -> list[str]:
    return _all_fixtures_from_accessibility_nodes(_fixture_nodes(page))


def _fixture_nodes(page) -> list[dict[str, Any]]:
    return page.evaluate(r"""() => {
      const styleForText = (container, token) => {
        const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
        const needle = token.toUpperCase();
        let node;
        while ((node = walker.nextNode())) {
          const text = node.nodeValue || '';
          const index = text.toUpperCase().indexOf(needle);
          if (index < 0) continue;
          const range = document.createRange();
          range.setStart(node, index);
          range.setEnd(node, index + token.length);
          const rect = range.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          const style = getComputedStyle(node.parentElement || container);
          let opacity = 1;
          for (let el = node.parentElement; el; el = el.parentElement) {
            opacity *= Number.parseFloat(getComputedStyle(el).opacity || '1');
            if (el === container) break;
          }
          return {color: style.color, opacity};
        }
        return null;
      };
      const out = [];
      const pending = [document];
      while (pending.length) {
        const root = pending.pop();
        for (const el of root.querySelectorAll('*')) {
          if (el.shadowRoot) pending.push(el.shadowRoot);
          if (!(el.matches('[role="button"], flt-semantics[aria-label], [aria-label]'))) continue;
          const label = (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim();
          if (!label || label.length > 120) continue;
          const r = el.getBoundingClientRect();
          const teams = [...label.toUpperCase().matchAll(/\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b/g)]
            .flatMap(match => [match[1], match[2]]);
          const teamStyles = {};
          for (const team of new Set(teams)) {
            const style = styleForText(el, team);
            if (style) teamStyles[team] = style;
          }
          out.push({
            label,
            y: r.top + window.scrollY,
            viewport_y: r.top + r.height / 2,
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
            team_styles: teamStyles
          });
        }
      }
      return out;
    }""")

def _record_fixture_statuses(
    nodes: list[dict[str, Any]],
    screenshot_status: dict[str, dict[str, bool | None]],
    eligibility_by_fixture: dict[str, dict[str, bool | None]],
) -> None:
    """Merge status observations without replacing a known status with unknown."""
    for item in nodes:
        label = " ".join(str(item.get("label", "")).split())
        match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", label, re.I)
        if not match:
            continue
        teams = (match.group(1).upper(), match.group(2).upper())
        styles = item.get("team_styles") or {}
        key = _fixture_status_key(label)
        pair_key = _fixture_pair_key(label)
        statuses = eligibility_by_fixture.setdefault(
            key, eligibility_by_fixture.get(pair_key, {})
        )
        observed = screenshot_status.get(key) or screenshot_status.get(pair_key, {})
        for team in teams:
            status = _resolve_fixture_team_status(team, styles, observed)
            if status is not None or team not in statuses:
                statuses[team] = status
        eligibility_by_fixture[pair_key] = statuses


def _advance_fixture_carousel(page) -> bool:
    """Use real wheel input and verify that visible fixture cards actually moved.

    Setting scrollLeft on Flutter's semantics overlay can move its transparent
    accessibility nodes without moving the rendered canvas. Compare visible
    card coordinates after each real input and report progress only when the
    viewport truly changes.
    """
    game_re = re.compile(r"\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b", re.I)

    def positions(nodes: list[dict[str, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for item in nodes:
            label = " ".join(str(item.get("label", "")).split())
            if not game_re.search(label):
                continue
            out[label] = (float(item.get("left", 0)) + float(item.get("right", 0))) / 2
        return out

    before = positions(_fixture_nodes(page))
    if not before:
        return False
    try:
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        page.mouse.move(min(float(viewport["width"]) * 0.48, 700), min(155, float(viewport["height"]) - 1))
        page.mouse.wheel(650, 0)
        page.wait_for_timeout(220)
        after = positions(_fixture_nodes(page))
        common = set(before) & set(after)
        shifts = [after[label] - before[label] for label in common]
        if shifts and max(abs(value) for value in shifts) >= 35:
            return True

        # Some Flutter builds translate horizontal wheel input into vertical
        # scrolling only. Try the keyboard carousel affordance as a fallback.
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(220)
        after = positions(_fixture_nodes(page))
        common = set(before) & set(after)
        shifts = [after[label] - before[label] for label in common]
        return bool(shifts and max(abs(value) for value in shifts) >= 35)
    except Exception:
        return False


def _scan_fixture_list(page, turn_number: int | None, *, max_steps: int = 20) -> tuple[list[str], list[str], dict[str, int], dict[str, dict[str, bool | None]]]:
    """Read all fixture labels and visible status colors across the carousel.

    Fixture cards are rendered in a horizontal Flutter carousel. Scrolling the
    whole page vertically moves the labels away from the screenshot used for
    color classification and caused OCR to borrow the status of a different
    team with the same abbreviation. Keep the carousel in view and advance it
    horizontally, merging observations from each visible slice.
    """
    batches: list[list[dict[str, Any]]] = []
    eligibility_by_fixture: dict[str, dict[str, bool | None]] = {}
    stalled = 0
    seen_labels: set[str] = set()
    did_selection_refresh = False
    for _ in range(max_steps):
        nodes = _fixture_nodes(page)
        if nodes:
            batches.append(nodes)
            seen_labels.update(" ".join(str(item.get("label", "")).split()) for item in nodes)
            screenshot_status = _fixture_statuses_from_screenshot(page, nodes)
            _record_fixture_statuses(nodes, screenshot_status, eligibility_by_fixture)
            # The page opens with its first card selected, displayed as white
            # text on a dark tile. That visual state is not an eligibility
            # color. Select a different, fully classified visible fixture once
            # so the initially selected card becomes readable on the next
            # screenshot. Previously observed statuses are not overwritten by
            # the newly selected card's deliberately unknown white text.
            if not did_selection_refresh:
                did_selection_refresh = True
                target_to_select = None
                for item in nodes:
                    label = " ".join(str(item.get("label", "")).split())
                    match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", label, re.I)
                    if not match:
                        continue
                    rect_left = float(item.get("left", 0))
                    rect_right = float(item.get("right", 0))
                    if rect_right <= 245 or rect_left >= 1120:
                        continue
                    observed = screenshot_status.get(_fixture_status_key(label)) or screenshot_status.get(_fixture_pair_key(label), {})
                    first_status, second_status = observed.get(match.group(1).upper()), observed.get(match.group(2).upper())
                    if isinstance(first_status, bool) and isinstance(second_status, bool):
                        target_to_select = label
                        break
                if target_to_select:
                    _click_fixture(page, target_to_select)
                    page.wait_for_timeout(180)
                    refreshed_nodes = _fixture_nodes(page)
                    if refreshed_nodes:
                        batches.append(refreshed_nodes)
                        seen_labels.update(" ".join(str(item.get("label", "")).split()) for item in refreshed_nodes)
                        refreshed_status = _fixture_statuses_from_screenshot(page, refreshed_nodes)
                        _record_fixture_statuses(refreshed_nodes, refreshed_status, eligibility_by_fixture)
        if _advance_fixture_carousel(page):
            stalled = 0
            page.wait_for_timeout(220)
        else:
            # Capture the end-of-carousel viewport before stopping; it may
            # contain cards that were only partially visible in the prior pass.
            page.wait_for_timeout(120)
            final_nodes = _fixture_nodes(page)
            if final_nodes:
                batches.append(final_nodes)
                seen_labels.update(" ".join(str(item.get("label", "")).split()) for item in final_nodes)
                screenshot_status = _fixture_statuses_from_screenshot(page, final_nodes)
                _record_fixture_statuses(final_nodes, screenshot_status, eligibility_by_fixture)
            stalled += 1
            if stalled >= 1:
                break
    all_fixtures, target_fixtures = _fixture_labels_from_batches(batches, turn_number)
    return all_fixtures, target_fixtures, _fixture_turn_map_from_batches(batches), eligibility_by_fixture


def _fixture_team_eligibility(style: dict[str, Any] | None) -> bool | None:
    """Classify a genuinely visible DOM label; Flutter's transparent semantics are ignored."""
    if not style:
        return None
    color = str(style.get("color") or "")
    match = re.search(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)", color, re.I)
    try:
        opacity = float(style.get("opacity", 1.0))
    except (TypeError, ValueError):
        return None
    if not match or opacity < 0.95:
        return None
    red, green, blue = (int(match.group(i)) for i in (1, 2, 3))
    alpha = float(match.group(4)) if match.group(4) is not None else 1.0
    effective_opacity = opacity * alpha
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    if effective_opacity >= 0.95 and luminance <= 75:
        return True
    if effective_opacity >= 0.95 and luminance >= 120:
        return False
    return None


def _resolve_fixture_team_status(
    team: str,
    dom_styles: dict[str, dict[str, Any]] | None,
    screenshot_statuses: dict[str, bool | None] | None,
) -> bool | None:
    """Prefer a visible DOM color and use OCR only as a fallback.

    Flutter semantics can expose transparent text, so the DOM classifier may
    return None. A confidently rendered DOM color then wins over OCR, whose
    small glyph boxes can be sensitive to anti-aliasing.
    """
    dom_status = _fixture_team_eligibility((dom_styles or {}).get(team))
    if dom_status is not None:
        return dom_status
    screenshot_status = (screenshot_statuses or {}).get(team)
    return screenshot_status if isinstance(screenshot_status, bool) else None


def _decode_png_rgb(image: bytes) -> tuple[int, int, bytearray] | None:
    """Decode 8-bit RGB/RGBA PNG screenshot pixels without optional imaging packages."""
    if not image.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    width = height = bit_depth = color_type = 0
    compressed = bytearray()
    while offset + 12 <= len(image):
        size = struct.unpack(">I", image[offset : offset + 4])[0]
        kind = image[offset + 4 : offset + 8]
        data = image[offset + 8 : offset + 8 + size]
        offset += size + 12
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
                return None
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    if not width or not height:
        return None
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    decoded = bytearray(height * stride)

    def paeth(left: int, up: int, upper_left: int) -> int:
        estimate = left + up - upper_left
        dl, du, dul = abs(estimate - left), abs(estimate - up), abs(estimate - upper_left)
        return left if dl <= du and dl <= dul else up if du <= dul else upper_left

    source = 0
    for y in range(height):
        filter_type = raw[source]
        source += 1
        row_start = y * stride
        previous_start = row_start - stride
        for x in range(stride):
            value = raw[source + x]
            left = decoded[row_start + x - channels] if x >= channels else 0
            up = decoded[previous_start + x] if y else 0
            upper_left = decoded[previous_start + x - channels] if y and x >= channels else 0
            if filter_type == 1:
                value = (value + left) & 255
            elif filter_type == 2:
                value = (value + up) & 255
            elif filter_type == 3:
                value = (value + ((left + up) // 2)) & 255
            elif filter_type == 4:
                value = (value + paeth(left, up, upper_left)) & 255
            elif filter_type != 0:
                return None
            decoded[row_start + x] = value
        source += stride
    if channels == 4:
        rgb = bytearray(width * height * 3)
        for pixel_index in range(width * height):
            source_index = pixel_index * 4
            target_index = pixel_index * 3
            alpha = decoded[source_index + 3]
            for channel in range(3):
                rgb[target_index + channel] = (
                    decoded[source_index + channel] * alpha + 255 * (255 - alpha)
                ) // 255
        decoded = rgb
    return width, height, decoded


def _visible_word_luminance(
    pixels: tuple[int, int, bytearray], box: tuple[int, int, int, int]
) -> float | None:
    width, height, data = pixels
    left, top, right, bottom = box
    left, right = max(0, left), min(width, right)
    top, bottom = max(0, top), min(height, bottom)
    if right <= left or bottom <= top:
        return None
    brightnesses = []
    for y in range(top, bottom):
        for x in range(left, right):
            index = (y * width + x) * 3
            value = int(0.2126 * data[index] + 0.7152 * data[index + 1] + 0.0722 * data[index + 2])
            if value < 235:
                brightnesses.append(value)
    if len(brightnesses) < 3:
        return None

    # A selected fixture is rendered as white text on a dark tile. Its dark
    # background must not be mistaken for black text (eligible). Estimate the
    # local background from a narrow ring around the OCR word rectangle and
    # leave text-on-dark tiles unclassified; they can be read after selection
    # moves to another fixture.
    ring = []
    for y in range(max(0, top - 4), min(height, bottom + 4)):
        for x in range(max(0, left - 4), min(width, right + 4)):
            if left <= x < right and top <= y < bottom:
                continue
            index = (y * width + x) * 3
            ring.append(int(0.2126 * data[index] + 0.7152 * data[index + 1] + 0.0722 * data[index + 2]))
    if len(ring) < 3 or sorted(ring)[len(ring) // 2] < 120:
        return None

    # OCR boxes include anti-aliased edge pixels as well as the glyph core.
    # The lower decile of non-background pixels is a useful discriminator for
    # black labels (dark glyph core) versus gray, disabled labels. Keep a gray
    # uncertainty band instead of fabricating a boolean near the threshold.
    brightnesses.sort()
    percentile_index = int((len(brightnesses) - 1) * 0.10)
    return float(brightnesses[percentile_index])


def _fixture_status_from_luminance(luminance: float | None) -> bool | None:
    """Convert measured text luminance to status, leaving borderline pixels unknown."""
    if luminance is None:
        return None
    if luminance <= 90:
        return True
    if luminance >= 110:
        return False
    return None


def _normalize_ocr_team_code(value: object) -> str | None:
    """Recover common Tesseract confusions without fuzzy-matching arbitrary codes."""
    token = re.sub(r"[^A-Z]", "", str(value or "").upper())
    variants = [token]
    # On away-team labels, Tesseract often reads the leading '@' as O/E. It
    # also confuses the Y in NYK with V, so ONVK becomes NYK after two known
    # visual normalizations. Accept a result only if it is an actual NBA code.
    if len(token) == 4 and token[0] in {"O", "E"}:
        variants.append(token[1:])
    variants.extend(candidate.replace("V", "Y") for candidate in tuple(variants))
    for candidate in variants:
        if candidate in TEAM_CODES:
            return candidate
    return None


def _fixture_card_pixel_status(
    pixels: tuple[int, int, bytearray],
    item: dict[str, Any],
    team_index: int,
    *,
    scale: float = 1.0,
) -> bool | None:
    """Read a team label from its own visible card when OCR yields no token.

    Fixture cards have a stable two-row layout: the first team is above the
    second, centered within each card. Sample a narrow region around the text
    line, never a different card. Return unknown for clipped cards, side ads,
    and the selected dark tile.
    """
    width, height, _ = pixels
    try:
        left, right, top, bottom = (
            float(item[key]) for key in ("left", "right", "top", "bottom")
        )
    except (KeyError, TypeError, ValueError):
        return None
    if team_index not in {0, 1} or right - left < 50 or bottom - top < 60:
        return None
    left_px, right_px = left * scale, right * scale
    # Keep inference inside the central Lineups canvas, excluding navigation
    # and the right-side advertisement even if semantics nodes overflow it.
    if left_px < 220 * scale or right_px > width - 300 * scale:
        return None
    center_x = ((left + right) / 2) * scale
    row_top = (top + (56 if team_index == 0 else 74)) * scale
    box = (
        round(center_x - 12 * scale),
        round(row_top),
        round(center_x + 12 * scale),
        round(row_top + 12 * scale),
    )
    return _fixture_status_from_luminance(_visible_word_luminance(pixels, box))


def _fixture_statuses_from_screenshot(
    page, nodes: list[dict[str, Any]]
) -> dict[str, dict[str, bool | None]]:
    """Use OCR boxes plus actual rendered text pixels to read black/gray eligibility."""
    executable = shutil.which("tesseract")
    if not executable or not nodes:
        return {}
    try:
        image = page.screenshot(full_page=False)
        result = subprocess.run(
            [executable, "stdin", "stdout", "tsv", "--psm", "11"],
            input=image,
            capture_output=True,
            check=False,
            timeout=12,
        )
        if result.returncode != 0:
            return {}
        pixels = _decode_png_rgb(image)
        if pixels is None:
            return {}
        rows = list(csv.DictReader(io.StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t"))
        image_width = pixels[0]
        scale = image_width / float(page.viewport_size["width"])
        words = []
        for row in rows:
            if row.get("level") != "5" or float(row.get("conf") or -1) < 25:
                continue
            token = _normalize_ocr_team_code(row.get("text", ""))
            if token is None:
                continue
            try:
                x, y = int(row["left"]), int(row["top"])
                w, h = int(row["width"]), int(row["height"])
            except (KeyError, TypeError, ValueError):
                continue
            luminance = _visible_word_luminance(pixels, (x, y, x + w, y + h))
            status = _fixture_status_from_luminance(luminance)
            words.append({"team": token, "x": x + w / 2, "y": y + h / 2, "status": status})

        statuses: dict[str, dict[str, bool | None]] = {}
        for item in nodes:
            label = " ".join(str(item.get("label", "")).split())
            match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", label, re.I)
            if not match:
                continue
            first, second = match.group(1).upper(), match.group(2).upper()
            center_y = float(item.get("viewport_y", 0)) * scale
            left = float(item.get("left", 0)) * scale - 10
            right = float(item.get("right", 0)) * scale + 10
            entry: dict[str, bool | None] = {}
            for team_index, team in enumerate((first, second)):
                nearby = [word for word in words if word["team"] == team and left <= word["x"] <= right]
                # Do not borrow an identically named team from another card.
                # Off-screen cards remain unknown until the carousel is moved
                # and the correct label is actually visible to OCR.
                status: bool | None = None
                if nearby:
                    chosen = min(nearby, key=lambda word: abs(word["y"] - center_y))
                    if abs(chosen["y"] - center_y) <= max(30.0, float(item.get("bottom", 0) - item.get("top", 0)) * scale):
                        status = chosen["status"]
                if status is None:
                    status = _fixture_card_pixel_status(pixels, item, team_index, scale=scale)
                if status is not None or nearby:
                    entry[team] = status
            if entry:
                statuses[_fixture_status_key(label)] = entry
                statuses[_fixture_pair_key(label)] = entry
        return statuses
    except Exception:
        return {}


def _reset_scrollables(page) -> None:
    page.evaluate("""() => {
      const roots = [document.scrollingElement], pending = [document];
      while (pending.length) {
        const root = pending.pop();
        for (const el of root.querySelectorAll('*')) {
          roots.push(el);
          if (el.shadowRoot) pending.push(el.shadowRoot);
        }
      }
      for (const el of roots) if (el) { el.scrollTop = 0; el.scrollLeft = 0; }
      window.scrollTo(0, 0);
    }""")
    # Flutter sometimes keeps its own scroll position even after the DOM
    # containers are reset. Home/negative-wheel return the schedule carousel
    # and the page to the first matchup before traversal starts.
    for _ in range(3):
        page.mouse.wheel(-2400, -2400)
        page.keyboard.press("Home")
    page.wait_for_timeout(250)


def _advance_fixture_scroll(page) -> None:
    """Advance the scroll container that owns fixture controls, not every pane."""
    moved = page.evaluate(r"""() => {
      const roots = [document], pending = [document], controls = [], candidates = new Map();
      const game = /\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b/i;
      while (pending.length) {
        const root = pending.pop();
        for (const el of root.querySelectorAll('*')) {
          if (el.shadowRoot) pending.push(el.shadowRoot);
          const label = (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim();
          if (label && label.length <= 140 && game.test(label)) controls.push(el);
        }
      }
      for (const control of controls) {
        let el = control, depth = 0;
        while (el && depth++ < 12) {
          const canY = el.scrollHeight > el.clientHeight + 8;
          const canX = el.scrollWidth > el.clientWidth + 8;
          if (canY || canX) candidates.set(el, (candidates.get(el) || 0) + 1);
          el = el.parentElement || el.getRootNode()?.host || null;
        }
      }
      if (!candidates.size && document.scrollingElement?.scrollHeight > document.scrollingElement?.clientHeight + 8)
        candidates.set(document.scrollingElement, 0);
      // Fixture cards live in a horizontal carousel. Prefer scrollable
      // ancestors that can move horizontally; otherwise vertical page scrolling
      // can move the lineup instead of exposing the next fixture card.
      const ordered = [...candidates.entries()].sort((a, b) => {
        const ax = a[0].scrollWidth > a[0].clientWidth + 8;
        const bx = b[0].scrollWidth > b[0].clientWidth + 8;
        return Number(bx) - Number(ax) || b[1] - a[1];
      });
      for (const [el] of ordered) {
        const maxX = el.scrollWidth - el.clientWidth;
        if (maxX > 8 && el.scrollLeft < maxX - 2) {
          const before = el.scrollLeft;
          el.scrollLeft = Math.min(maxX, before + Math.max(220, Math.floor(el.clientWidth * 0.6)));
          if (el.scrollLeft > before + 1) return true;
        }
        const maxY = el.scrollHeight - el.clientHeight;
        if (maxY > 8 && el.scrollTop < maxY - 2) {
          const before = el.scrollTop;
          el.scrollTop = Math.min(maxY, before + Math.max(220, Math.floor(el.clientHeight * 0.6)));
          if (el.scrollTop > before + 1) return true;
        }
      }
      return false;
    }""")
    if not moved:
        page.mouse.move(0.5 * page.viewport_size["width"], 0.35 * page.viewport_size["height"])
        page.mouse.wheel(0, 540)
        page.mouse.wheel(540, 0)
        page.keyboard.press("PageDown")
    page.wait_for_timeout(180)


def _click_fixture(page, fixture_label: str, *, max_steps: int = 50) -> bool:
    matchup = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
    if not matchup:
        return False
    first, second = matchup.group(1), matchup.group(2)
    pattern = re.compile(rf"\b{first}\s+(?:VS|@)\s+{second}\b", re.I)
    date = re.search(r"\b\d{1,2}/\d{1,2}\b", fixture_label)
    for _ in range(max_steps):
        # Prefer the accessible role when Flutter exposes it. Force is needed
        # for cards clipped by the horizontal game carousel.
        try:
            buttons = page.get_by_role("button", name=pattern)
            count = buttons.count()
            if count:
                button_candidates = buttons.all()
                chosen = None
                for candidate in button_candidates:
                    name = (candidate.get_attribute("aria-label", timeout=250) or
                            candidate.inner_text(timeout=250) or "").strip()
                    if date and date.group(0) not in name:
                        continue
                    chosen = candidate
                    break
                # If the accessible label omits the date, do not silently click
                # the first same-matchup control from another round/virtual card;
                # let the DOM-coordinate fallback inspect date-qualified labels.
                if chosen is None:
                    raise LookupError("nessun controllo con data corrispondente")
                # Fixture cards may remain in Flutter's virtualized carousel
                # after the previous lineup scan scrolled the page. A forced
                # click does not reliably bring an off-screen semantics node
                # into the hit-test area, so scroll the selected card into view
                # first and only then activate it.
                chosen.scroll_into_view_if_needed(timeout=1500)
                # Use a real hit-tested pointer click. `force=True` can report
                # success while bypassing Flutter's pointer routing, leaving
                # the previously selected fixture active and no market request.
                chosen.click(timeout=2500)
                page.wait_for_timeout(650)
                return True
        except Exception:
            pass
        # Some Flutter builds expose fixture labels as semantics text rather
        # than buttons. Playwright's text locator can still activate the
        # semantics overlay where clicking the host element does not.
        try:
            text_controls = page.get_by_text(pattern)
            count = text_controls.count()
            for index in range(min(count, 8)):
                control = text_controls.nth(index)
                label = (control.inner_text(timeout=250) or "").strip()
                if date and date.group(0) not in label:
                    continue
                control.scroll_into_view_if_needed(timeout=1000)
                # Do not bypass hit-testing on Flutter semantics overlays.
                control.click(timeout=1500)
                page.wait_for_timeout(650)
                return True
        except Exception:
            pass
        # Flutter's semantics controls do not always expose a Playwright button
        # role. Activate the actual accessibility node, then fall back to its
        # rendered hit target.
        try:
            activated = page.evaluate("""(target) => {
              const pending = [document], nodes = [];
              while (pending.length) {
                const root = pending.pop();
                for (const el of root.querySelectorAll('*')) {
                  if (el.shadowRoot) pending.push(el.shadowRoot);
                  if (!el.matches('flt-semantics[aria-label], [role="button"], [aria-label]')) continue;
                  const label = (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim();
                  if (!label || label.length > 140) continue;
                  const re = new RegExp('\\\\b' + target.first + '\\\\s+(?:VS|@)\\\\s+' + target.second + '\\\\b', 'i');
                  if (!re.test(label)) continue;
                  const rect = el.getBoundingClientRect();
                  if (rect.width < 2 || rect.height < 2) continue;
                  nodes.push({el, label,
                    dateMatch: !target.date || label.includes(target.date),
                    priority: (el.getAttribute('role') === 'button' || el.tagName === 'FLT-SEMANTICS' ? 0 : 1) + label.length / 1000});
                }
              }
              const dated = nodes.filter(n => n.dateMatch);
              // If the caller supplied a date, never activate a same-matchup
              // control from another card just because no exact date was found.
              const choices = (target.date ? dated : nodes).sort((a, b) => a.priority - b.priority);
              if (!choices.length) return null;
              const choice = choices[0];
              choice.el.scrollIntoView({block: 'center', inline: 'center'});
              const rect = choice.el.getBoundingClientRect();
              return {label: choice.label, x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2};
            }""", {
                "first": first,
                "second": second,
                "date": date.group(0) if date else "",
            })
            if activated:
                # A real browser input event reaches Flutter's pointer router;
                # HTMLElement.click()/synthetic MouseEvents often do not.
                page.mouse.click(activated["x"], activated["y"], timeout=1500)
                page.wait_for_timeout(650)
                return True
        except Exception:
            pass
        matching = []
        dated = []
        for selector in ('[role="button"]', 'flt-semantics[aria-label]', '[aria-label]'):
            try:
                for control in page.locator(selector).all():
                    label = (control.get_attribute("aria-label", timeout=200) or
                             control.inner_text(timeout=200)).strip()
                    if pattern.search(label):
                        matching.append(control)
                        if date is not None and date.group(0) in label:
                            dated.append(control)
            except Exception:
                continue
        candidates = dated or matching
        for control in candidates:
            try:
                control.scroll_into_view_if_needed(timeout=1000)
                control.click(timeout=1500)
                page.wait_for_timeout(450)
                return True
            except Exception:
                continue
        _advance_fixture_scroll(page)
    return False


def _fixture_click_diagnostic(page, fixture_label: str) -> str:
    """Summarize matching controls after a failed click without leaking auth data."""
    try:
        matchup = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
        if not matchup:
            return "etichetta non interpretabile"
        result = page.evaluate("""(target) => {
          const pending = [document], found = [];
          while (pending.length) {
            const root = pending.pop();
            for (const el of root.querySelectorAll('*')) {
              if (el.shadowRoot) pending.push(el.shadowRoot);
              const label = (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim();
              if (!label || label.length > 140) continue;
              if (label.toUpperCase().includes(target.first.toUpperCase()) &&
                  label.toUpperCase().includes(target.second.toUpperCase())) {
                const rect = el.getBoundingClientRect();
                const scrollParents = [];
                let parent = el.parentElement, depth = 0;
                while (parent && depth++ < 8) {
                  if (parent.scrollWidth > parent.clientWidth + 8 || parent.scrollHeight > parent.clientHeight + 8) {
                    scrollParents.push({tag: parent.tagName.toLowerCase(),
                      x: Math.round(parent.scrollLeft), y: Math.round(parent.scrollTop),
                      cw: parent.clientWidth, sw: parent.scrollWidth,
                      ch: parent.clientHeight, sh: parent.scrollHeight});
                  }
                  parent = parent.parentElement || parent.getRootNode()?.host || null;
                }
                found.push({tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '',
                  label: label.slice(0, 90), x: Math.round(rect.left), y: Math.round(rect.top),
                  width: Math.round(rect.width), height: Math.round(rect.height),
                  inViewport: rect.right > 0 && rect.bottom > 0 && rect.left < innerWidth && rect.top < innerHeight,
                  scrollParents});
              }
            }
          }
          return found.slice(0, 5);
        }""", {"first": matchup.group(1), "second": matchup.group(2)})
        return f"controlli DOM corrispondenti={result!r}"
    except Exception as exc:
        return f"diagnostica click non disponibile ({type(exc).__name__})"


def _match_unavailable_to_market(
    annotation: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Resolve a Flutter INDISPONIBILI label to exactly one market player row."""
    role = annotation.get("role") or "ANY"
    team = str(annotation.get("team") or "").upper()
    ui_name = str(annotation.get("ui_name") or "").strip()
    surname = player_surname(ui_name) or player_surname(annotation.get("surname") or "")
    ui_key = player_key(ui_name)
    ui_tokens = ui_key.split()
    ui_initial = ui_tokens[0][0] if ui_tokens else ""
    annotation_cr = annotation.get("cr")
    try:
        annotation_cr = float(annotation_cr) if annotation_cr is not None else None
    except (TypeError, ValueError):
        annotation_cr = None

    # The browser captures one API response per fixture, so the same player
    # can occur many times in ``rows``. Resolve identity against a deduplicated
    # pool; otherwise a unique surname looks ambiguous merely because its API
    # record was repeated across fixtures. Keep the last object for each
    # canonical identity, matching the later market deduplication order.
    pool_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("role") == "HC":
            continue
        identity = (
            player_key(row.get("player_name")),
            str(row.get("team") or "").strip().upper(),
            str(row.get("role") or "").strip().upper(),
        )
        if all(identity):
            pool_by_identity[identity] = row
    pool = list(pool_by_identity.values())

    def by_key(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not ui_key:
            return []
        return [row for row in items if player_key(row.get("player_name")) == ui_key]

    def by_surname(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not surname:
            return []
        return [row for row in items if player_surname(row.get("player_name")) == surname]

    def by_token(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not surname:
            return []
        hits = []
        for row in items:
            tokens = player_key(row.get("player_name")).split()
            if surname in tokens:
                hits.append(row)
        return hits

    def by_initial_surname(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Match abbreviated forms like 'J. Embiid' / 'Embiid' to full market names."""
        if not surname:
            return []
        hits = []
        for row in items:
            tokens = player_key(row.get("player_name")).split()
            if not tokens or tokens[-1] != surname:
                continue
            if not ui_initial or len(ui_tokens) == 1:
                hits.append(row)
            elif tokens[0].startswith(ui_initial):
                hits.append(row)
        return hits

    def by_cr(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if annotation_cr is None:
            return []
        hits = []
        for row in items:
            try:
                if abs(float(row.get("cr")) - annotation_cr) < 0.05:
                    hits.append(row)
            except (TypeError, ValueError):
                continue
        return hits

    def pick(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # Soft disambiguation: annotation CR, then UI role, then refuse.
        if annotation_cr is not None:
            priced = by_cr(candidates)
            if len(priced) == 1:
                return priced[0]
        if role not in {"ANY", ""}:
            role_hits = [row for row in candidates if row.get("role") == role]
            if len(role_hits) == 1:
                return role_hits[0]
        return None

    team_pool = [row for row in pool if str(row.get("team") or "").upper() == team] if team else []
    stages = [
        by_key(team_pool),
        by_initial_surname(team_pool),
        by_surname(team_pool),
        by_token(team_pool),
        by_key(pool),
        by_initial_surname(pool),
        by_surname(pool),
        by_token(pool),
    ]
    for candidates in stages:
        chosen = pick(candidates)
        if chosen is not None:
            return chosen
    return None


def _filter_plausible_unavailable_annotations(
    annotations: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop unscoped UI/ad fragments that cannot be a surname in the market.

    The Flutter unavailable panel sometimes includes rotating advertising text
    with no team context. Preserve ambiguous labels such as Sharpe/Miller when
    their surname exists in the market, but do not report arbitrary ad words as
    unresolved player identities.
    """
    market_surnames = {
        player_surname(row.get("player_name"))
        for row in rows
        if str(row.get("role", "")).strip().upper() != "HC"
        and player_surname(row.get("player_name"))
    }
    plausible: list[dict[str, Any]] = []
    for item in annotations:
        if item.get("lineup_group") != "INDISPONIBILI":
            continue
        team = str(item.get("team") or "").strip()
        surname = player_surname(item.get("ui_name") or item.get("surname"))
        if team or surname in market_surnames:
            plausible.append(item)
    return plausible


def _apply_lineup_annotations(
    rows: list[dict[str, Any]], annotations: list[dict[str, Any]], coach_names: dict[str, str] | None = None
) -> tuple[int, int]:
    """Attach short Flutter names to canonical API/snapshot market records."""
    coach_names = coach_names or {}
    matched = unavailable = 0
    for annotation in annotations:
        team, role, surname = annotation["team"], annotation["role"], annotation["surname"]
        group = annotation["lineup_group"]
        ui_name = str(annotation.get("ui_name") or "").casefold()
        if group == "INDISPONIBILI":
            row = _match_unavailable_to_market(annotation, rows)
            if row is None:
                continue
            row["lineup_group"] = group
            row["status"] = "OUT"
            unavailable += 1
            matched += 1
            continue
        if role == "ANY":
            candidates = [
                row for row in rows
                if row["team"] == team
                and (player_key(row["player_name"]) == player_key(ui_name)
                     or player_surname(row["player_name"]) == player_surname(surname or ui_name))
            ]
        else:
            candidates = [
                row for row in rows
                if row["team"] == team
                and row["role"] == role
                and player_surname(row["player_name"]) == player_surname(surname or ui_name)
            ]
        # The two visual columns can be reversed relative to the fixture label,
        # but a lineup annotation must never be attached to a player outside the
        # two teams in that fixture.
        fixture_teams = {
            str(value).strip().upper()
            for value in annotation.get("_fixture_teams", [])
            if str(value).strip()
        }
        if not candidates and role == "ANY":
            candidates = [
                row for row in rows
                if row["role"] != "HC"
                and (not fixture_teams or str(row["team"]).upper() in fixture_teams)
                and player_surname(row["player_name"]) == player_surname(surname or ui_name)
            ]
        elif not candidates and role != "HC":
            candidates = [
                row for row in rows
                if row["role"] == role
                and (not fixture_teams or str(row["team"]).upper() in fixture_teams)
                and player_surname(row["player_name"]) == player_surname(surname or ui_name)
            ]
        if role != "HC" and len(candidates) > 1:
            try:
                annotation_cr = float(annotation.get("cr"))
            except (TypeError, ValueError):
                annotation_cr = float("nan")
            if math.isfinite(annotation_cr):
                price_hits = []
                for candidate in candidates:
                    try:
                        if abs(float(candidate.get("cr")) - annotation_cr) < 0.05:
                            price_hits.append(candidate)
                    except (TypeError, ValueError):
                        continue
                if len(price_hits) == 1:
                    candidates = price_hits
        if role == "HC":
            full_name = coach_names.get(team, surname.title())
            if player_surname(full_name) == player_surname(surname):
                candidates = [
                    row for row in rows
                    if row["team"] == team and row["role"] == "HC"
                    and player_key(row["player_name"]) == player_key(full_name)
                ]
                if not candidates:
                    candidates = [row for row in rows if row["team"] == team and row["role"] == "HC"]
                if not candidates:
                    candidates = [{"player_name": full_name, "cr": annotation.get("cr"), "team": team, "role": "HC"}]
                    rows.extend(candidates)
        if role != "HC" and annotation.get("cr") is not None:
            candidates = [row for row in candidates if abs(float(row.get("cr", 0) or 0) - annotation["cr"]) < 0.11]
        if len(candidates) != 1:
            continue
        row = candidates[0]
        # The same player can appear in multiple fixture cards. A later
        # starter/bench annotation must never overwrite an OUT observation
        # already collected from the league-wide INDISPONIBILI panel.
        if group != "INDISPONIBILI" and str(row.get("status") or "").strip().upper() in {
            "OUT", "INJURED", "UNAVAILABLE", "INDISPONIBILE"
        }:
            matched += 1
            continue
        if annotation.get("cr") is not None:
            row["cr"] = annotation["cr"]
        row["lineup_group"] = group
        if role != "HC":
            row["starter"] = "true" if group == "QUINTETTO" else "false" if group == "PANCHINA" else ""
            row["status"] = "AVAILABLE"
        matched += 1
    return matched, unavailable


def _enable_flutter_accessibility(page) -> None:
    """Activate Flutter semantics, including its shadow-DOM placeholder."""
    # Flutter keeps the initial accessibility prompt inside flt-glass-pane's
    # shadow root, where ordinary role/text locators cannot always find it.
    try:
        clicked = page.evaluate("""() => {
          const pending = [document];
          while (pending.length) {
            const root = pending.pop();
            for (const el of root.querySelectorAll('*')) {
              if (el.shadowRoot) pending.push(el.shadowRoot);
              if (el.tagName?.toLowerCase() === 'flt-semantics-placeholder') {
                el.click(); return true;
              }
            }
          }
          return false;
        }""")
        if clicked:
            page.wait_for_timeout(700)
            return
    except Exception:
        pass
    candidates = (
        page.get_by_role("button", name=re.compile("enable accessibility", re.I)),
        page.get_by_text(re.compile("enable accessibility", re.I)),
        page.locator('flt-semantics[aria-label*="accessibility" i]'),
    )
    for candidate in candidates:
        try:
            if candidate.count():
                candidate.first.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue
    # Flutter may activate accessibility semantics on keyboard navigation.
    for _ in range(2):
        try:
            page.keyboard.press("Tab")
            page.wait_for_timeout(250)
        except Exception:
            break


def _page_diagnostic(page, responses: list[tuple[str, int, Any]]) -> str:
    """Return actionable, non-sensitive state without exposing cookies/tokens."""
    try:
        url = page.url
        title = page.title()
        body = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=2000))[:500]
        roles = page.locator("[role], flt-semantics").count()
    except Exception as exc:
        return f"pagina non leggibile ({type(exc).__name__})"
    api = ", ".join(f"HTTP {status}" for _, status, _ in responses[-5:]) or "nessuna risposta API lineups"
    return f"URL={url!r}; titolo={title!r}; nodi accessibili={roles}; API={api}; testo={body!r}"


def _team_code(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("abbreviation") or value.get("code") or value.get("team_code") or value.get("name")
    code = str(value or "").strip().upper()
    return code if code in TEAM_CODES else ""


def _position(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("abbreviation") or value.get("id")
    return POSITION_MAP.get(str(value or "").strip().casefold(), "")


def _quotation(obj: dict[str, Any]) -> float | None:
    for key in ("quotation", "cr", "credits", "price"):
        if key in obj and obj[key] is not None:
            try:
                return float(str(obj[key]).replace(",", ".").replace(" CR", "").strip())
            except (TypeError, ValueError):
                return None
    return None


def _flatten_market(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def walk(node: Any, *, team_hint: str = "", coach_hint: bool = False) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, team_hint=team_hint, coach_hint=coach_hint)
            return
        if not isinstance(node, dict):
            return

        team_value = node.get("team") or node.get("nba_team") or node.get("team_code")
        team = _team_code(team_value) or team_hint
        first = str(node.get("first_name") or "").strip()
        last = str(node.get("last_name") or "").strip()
        name = " ".join(x for x in (first, last) if x).strip()
        if not name:
            name = str(node.get("name") or "").strip()

        position = _position(node.get("position") or node.get("position_id") or node.get("role"))
        is_coach = coach_hint or str(node.get("role") or node.get("position") or "").strip().casefold() in {
            "hc", "coach", "head coach", "allenatore"
        }
        cr = _quotation(node)
        if cr is not None and cr < 4:
            cr = None
        role = "HC" if is_coach else position
        if name and team and role and cr is not None:
            identity = (team, role, name.casefold())
            if identity not in seen:
                seen.add(identity)
                # Preserve identifiers supplied by the Lineups API for a
                # separate audit. Do not assume yet that they equal profile IDs.
                raw_entity_id = (
                    node.get("player_id")
                    or node.get("playerId")
                    or node.get("id")
                )
                entity_id = str(raw_entity_id).strip() if raw_entity_id is not None else ""
                if not entity_id.isdigit():
                    entity_id = ""
                slug = str(node.get("slug") or "").strip()
                row = {"player_name": name, "cr": cr, "team": team, "role": role}
                if entity_id:
                    row["lineups_entity_id"] = entity_id
                if slug:
                    row["lineups_entity_slug"] = slug
                rows.append(row)

        for key, child in node.items():
            child_team = team
            if key in {"home_team", "away_team", "team"}:
                child_team = _team_code(child) or team
            walk(
                child,
                team_hint=child_team,
                coach_hint=coach_hint or key.casefold() in {"coach", "head_coach", "head coach"},
            )

    walk(value)
    return rows


def _deduplicate_market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated API payloads before attaching UI lineup annotations.

    The same player may be returned in many fixture responses. Applying a
    surname annotation to that repeated list makes a single player look
    ambiguous, so keep one exact canonical row first. Raw name variants are
    intentionally preserved here; the downstream normalized-identity gate
    must still be able to reject genuinely ambiguous market identities.
    """
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        identity = (
            str(row.get("team") or "").strip().upper(),
            str(row.get("role") or "").strip().upper(),
            str(row.get("player_name") or "").strip().casefold(),
        )
        if all(identity):
            unique[identity] = row
    return list(unique.values())


def _fixture_lineup_coverage(
    annotations: list[dict[str, Any]], fixture_label: str, market_rows: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """Count only lineup labels that resolve to players on the expected NBA team.

    A successful API response for one fixture does not provide the canonical
    rosters for every other fixture. Matching observed surnames against the
    union of captured market responses detects stale panels before their labels
    can be attached to the wrong game.
    """
    match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
    if not match:
        return {}
    teams = (match.group(1).upper(), match.group(2).upper())
    names_by_team: dict[str, dict[str, list[dict[str, Any]]]] = {team: {} for team in teams}
    seen_market_identities: set[tuple[str, str]] = set()
    for row in market_rows:
        team = str(row.get("team") or "").strip().upper()
        if team not in names_by_team or str(row.get("role") or "").upper() == "HC":
            continue
        full_name = str(row.get("player_name") or "").strip()
        identity = (team, player_key(full_name))
        # The API response can repeat the same full-league market once per
        # fixture. Deduplicate canonical identities before resolving shared
        # surnames; otherwise repeated copies look like ambiguous players.
        if not full_name or not identity[1] or identity in seen_market_identities:
            continue
        seen_market_identities.add(identity)
        surname = player_surname(full_name)
        if surname:
            names_by_team[team].setdefault(surname, []).append(row)

    resolved: dict[str, dict[str, set[str]]] = {
        team: {"players": set(), "starters": set()} for team in teams
    }
    for annotation in annotations:
        observed_team = str(annotation.get("team") or "").strip().upper()
        group = str(annotation.get("lineup_group") or "").strip().upper()
        if group not in {"QUINTETTO", "PANCHINA"}:
            continue
        surname = player_surname(annotation.get("surname") or annotation.get("ui_name") or "")
        role = str(annotation.get("role") or "").strip().upper()
        try:
            annotation_cr = float(annotation.get("cr"))
        except (TypeError, ValueError):
            annotation_cr = float("nan")
        # The two rendered lineup columns can be reversed relative to the
        # fixture's abbreviated matchup label. Resolve a surname against both
        # expected rosters first; use visual column only to break cross-team
        # collisions. Within a team, use role and displayed CR to disambiguate
        # common surnames such as Jalen/Jaylin Williams.
        candidates: dict[str, dict[str, Any]] = {}
        for team in teams:
            hits = list(names_by_team[team].get(surname, []))
            if role:
                role_hits = [
                    row for row in hits
                    if str(row.get("role") or "").strip().upper() == role
                    or (role == "F" and str(row.get("role") or "").strip().upper() == "A")
                ]
                if role_hits:
                    hits = role_hits
            if len(hits) > 1 and math.isfinite(annotation_cr):
                price_hits = []
                for row in hits:
                    try:
                        if abs(float(row.get("cr")) - annotation_cr) < 0.05:
                            price_hits.append(row)
                    except (TypeError, ValueError):
                        continue
                if price_hits:
                    hits = price_hits
            if len(hits) == 1:
                candidates[team] = hits[0]
        if len(candidates) == 1:
            team, matched_row = next(iter(candidates.items()))
        elif len(candidates) > 1 and observed_team in candidates:
            team, matched_row = observed_team, candidates[observed_team]
        else:
            continue
        full_name = str(matched_row.get("player_name") or "").strip()
        if not full_name:
            continue
        resolved[team]["players"].add(full_name)
        if group == "QUINTETTO":
            resolved[team]["starters"].add(full_name)
    return {
        team: {"players": len(values["players"]), "starters": len(values["starters"])}
        for team, values in resolved.items()
    }


def _fixture_required_lineup_teams(
    fixture_label: str, eligibility_by_fixture: dict[str, dict[str, bool | None]] | None = None
) -> set[str]:
    """Require lineup coverage for teams Dunkest marks eligible in this turn.

    A fixture can contain a team explicitly disabled for the selected Dunkest
    turn. Such a side has no lineup panel to scrape; unknown eligibility is not
    treated as disabled and remains subject to validation.
    """
    match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
    if not match:
        return set()
    teams = {match.group(1).upper(), match.group(2).upper()}
    statuses = eligibility_by_fixture or {}
    observed = statuses.get(_fixture_status_key(fixture_label)) or statuses.get(
        _fixture_pair_key(fixture_label), {}
    )
    required = {team for team in teams if observed.get(team) is not False}
    return required if observed else teams


def _fixture_lineup_coverage_ok(
    coverage: dict[str, dict[str, int]], required_teams: set[str] | None = None
) -> bool:
    """Require five starters and eight roster labels for every eligible side."""
    required = set(required_teams) if required_teams is not None else set(coverage)
    return bool(required) and all(
        team in coverage
        and coverage[team].get("starters", 0) == 5
        and coverage[team].get("players", 0) >= 8
        for team in required
    )


def _fixture_present_in_market_response(
    responses: list[tuple[str, int, Any]], fixture_label: str, *, start: int = 0
) -> bool:
    """Check whether a Lineups response contains both teams of one matchup."""
    match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", fixture_label, re.I)
    if not match:
        return False
    expected = {match.group(1).upper(), match.group(2).upper()}
    return any(
        status == 200 and expected.issubset({row["team"] for row in _flatten_market(body)})
        for _, status, body in responses[start:] if body is not None
    )


def _latest_fixture_market_matches(
    responses: list[tuple[str, int, Any]], fixture_label: str
) -> bool:
    """Return true only when the most recent captured market belongs to this fixture.

    The eligibility warm-up can select a different fixture before scraping starts.
    A historical response proves that a fixture was loaded at some point, not that
    it is still selected now. Using the last response prevents collecting one
    fixture's annotations under another fixture's label.
    """
    return bool(responses) and _fixture_present_in_market_response(
        responses[-1:], fixture_label
    )


def _wait_for_fixture_market(page, responses, fixture_label: str, *, start: int, timeout_ms: int = 3500) -> bool:
    """Wait for the selected fixture's API data; a successful click alone is insufficient."""
    waited = 0
    while waited < timeout_ms:
        if _fixture_present_in_market_response(responses, fixture_label, start=start):
            return True
        interval = min(150, timeout_ms - waited)
        page.wait_for_timeout(interval)
        waited += interval
    return _fixture_present_in_market_response(responses, fixture_label, start=start)


def scrape_lineups_market(output: Path, *, turn_number: int | None = None, min_players: int = 250) -> Path:
    """Scrape the entire Dunkest gameweek in one browser session by default.

    Set ``turn_number`` to 1, 2, or 3 only for a deliberate single-turn capture.
    The default ``None`` visits every fixture across all three turns, while the
    league-wide API market and unavailability panel are captured once.
    A dedicated local Chromium profile persists the site's session between runs.
    The user signs in manually on first use; credentials are never read or saved
    by this application. The browser profile contains authentication state and
    must be treated as private local data.
    """
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    responses: list[tuple[str, int, Any]] = []
    ui_annotations: list[dict[str, Any]] = []

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright non è installato. Esegui: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        profile_dir = _lineups_browser_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            profile_dir.chmod(0o700)
        except OSError:
            # Some filesystems do not support POSIX permissions; the profile
            # still remains outside the repository by default.
            pass
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                # The wider viewport keeps the fixture carousel labels in the
                # captured image instead of underneath the right-side ad panel.
                # On the live 1440px viewport OCR missed several valid sides.
                viewport={"width": 1680, "height": 1000},
            )
        except PlaywrightError as exc:
            raise RuntimeError(
                "Non riesco ad aprire il profilo Chromium persistente per Lineups. "
                f"Chiudi eventuali finestre Chromium avviate dallo scraper e riprova. "
                f"Profilo: {profile_dir}. Dettaglio: {exc}"
            ) from exc
        page = context.new_page()

        def capture(response) -> None:
            if API_HOST not in response.url or not LINEUPS_PATH.search(response.url.split("?", 1)[0]):
                return
            try:
                responses.append((response.url, response.status, response.json()))
            except Exception:
                responses.append((response.url, response.status, None))

        page.on("response", capture)
        page.goto("https://fantasy.dunkest.com/1/lineups", wait_until="domcontentloaded")
        # Flutter initially renders a canvas and exposes an explicit accessibility
        # toggle. Enable it before asking the user to navigate; it is independent
        # of authentication and may otherwise never appear in Playwright's roles.
        page.wait_for_timeout(1200)
        _enable_flutter_accessibility(page)
        print("Scraping autonomo Dunkest Lineups avviato usando il profilo browser persistente.")
        print("Attendo il caricamento automatico della pagina e delle partite; nessun Invio richiesto.")

        # Do not block on terminal input. The persistent Chromium profile keeps
        # the authenticated session between runs; wait for Flutter's fixture
        # labels to become available, refreshing the accessibility layer while
        # the app initializes. If authentication has expired, fail with a
        # diagnostic instead of hanging for manual input.
        fixture_nodes_ready = False
        for attempt in range(45):
            _enable_flutter_accessibility(page)
            nodes = _fixture_nodes(page)
            if any(re.search(r"\b[A-Z]{3}\s+(?:VS|@)\s+[A-Z]{3}\b", str(node.get("label", "")), re.I) for node in nodes):
                fixture_nodes_ready = True
                break
            if attempt in {9, 19, 29}:
                print(f"Pagina Lineups ancora in caricamento ({attempt + 1}/45)...")
            page.wait_for_timeout(1000)

        if not fixture_nodes_ready:
            diagnostic = _page_diagnostic(page, responses)
            context.close()
            raise RuntimeError(
                "Lineups non è diventata disponibile automaticamente dopo 45 secondi. "
                "Lo scraper non richiede più Invio: controlla che il profilo browser persistente "
                "sia già autenticato e che Dunkest sia raggiungibile. Diagnostica: " + diagnostic
            )

        # Flutter may recreate its semantics overlay after initialization.
        _enable_flutter_accessibility(page)
        page.wait_for_timeout(500)
        fixture_labels, target_fixture_labels, fixture_turns, fixture_eligibility = _scan_fixture_list(page, turn_number)

        if not target_fixture_labels:
            diagnostic = _page_diagnostic(page, responses)
            context.close()
            scope = "della giornata" if turn_number is None else f"del TURNO {turn_number}"
            raise RuntimeError(
                f"Non trovo le partite {scope} nella pagina Lineups. "
                "Verifica che la pagina mostri tutti i turni della giornata e che "
                "l'accessibilità sia attiva. Diagnostica: " + diagnostic
            )

        # _scan_fixture_list deliberately selects a different card to classify
        # eligibility colors. Never infer the active card from the API payload:
        # /matches/{id}/lineups returns the league-wide player pool, so both
        # teams of every fixture are present even while a different card is open.
        # Each target card is clicked and its rendered lineup is verified below.
        _reset_scrollables(page)

        visited = 0
        target_visited = 0
        failed_fixtures: list[str] = []
        failed_lineup_fixtures: dict[str, dict[str, dict[str, int]]] = {}
        first_click_diagnostic = ""
        # Responses may be fixture-scoped or repeated full-market payloads.
        # Build a union to verify visible names against canonical team rosters.
        def current_market_reference_rows() -> list[dict[str, Any]]:
            reference: list[dict[str, Any]] = []
            for _, response_status, response_body in responses:
                if response_status == 200 and response_body is not None:
                    reference.extend(_flatten_market(response_body))
            return reference

        market_reference_rows = current_market_reference_rows()
        _reset_scrollables(page)
        for label in fixture_labels:
            is_target_fixture = label in target_fixture_labels
            clicked = False
            for attempt in range(3):
                clicked = _click_fixture(page, label)
                if clicked:
                    break
                if attempt < 2:
                    _advance_fixture_scroll(page)
                    page.wait_for_timeout(300)
            if not clicked:
                failed_fixtures.append(label)
                if not first_click_diagnostic:
                    first_click_diagnostic = _fixture_click_diagnostic(page, label)
                continue

            # A 200 response is not fixture-specific: verify the rendered
            # lineup by resolving its labels against the two expected rosters.
            # Retry selection/collection when the panel still belongs to a
            # different matchup, and fail closed rather than saving a partial
            # or cross-fixture market snapshot.
            scanned_annotations: list[dict[str, Any]] = []
            coverage: dict[str, dict[str, int]] = {}
            required_lineup_teams = _fixture_required_lineup_teams(label, fixture_eligibility)
            attempts = 3 if is_target_fixture else 1
            for annotation_attempt in range(attempts):
                if annotation_attempt > 0:
                    _advance_fixture_scroll(page)
                    page.wait_for_timeout(250)
                    _click_fixture(page, label)
                    page.wait_for_timeout(500)
                scanned_annotations = _scroll_collect_lineup_annotations(page, label)
                if not is_target_fixture or not required_lineup_teams:
                    break
                # Response capture is asynchronous; refresh the union after the
                # click/scroll so a just-loaded matchup contributes its own pool.
                market_reference_rows = current_market_reference_rows()
                coverage = _fixture_lineup_coverage(
                    scanned_annotations, label, market_reference_rows
                )
                if _fixture_lineup_coverage_ok(coverage, required_lineup_teams):
                    break
            lineup_verified = _fixture_lineup_coverage_ok(coverage, required_lineup_teams)
            if is_target_fixture and required_lineup_teams and not lineup_verified:
                failed_lineup_fixtures[label] = coverage
                sample = [
                    {"team": item.get("team"), "surname": item.get("surname"),
                     "role": item.get("role"), "group": item.get("lineup_group")}
                    for item in scanned_annotations[:16]
                ]
                print(
                    f"Lineup non verificata per {label}: richieste={sorted(required_lineup_teams)}; "
                    f"coverage={coverage}; annotazioni={sample}"
                )
                if not first_click_diagnostic:
                    first_click_diagnostic = _fixture_click_diagnostic(page, label)
                if turn_number is not None:
                    failed_fixtures.append(label)
                    continue
                # Full-gameweek mode preserves the complete market even if a
                # visual lineup is imperfect. Injury labels are not part of this scrape.
                target_visited += 1
                visited += 1
                continue

            if is_target_fixture:
                target_visited += 1
            # Lineups stores player/coach market annotations only. The separate
            # official injuries route owns all injury and rest classifications.
            if is_target_fixture and required_lineup_teams and lineup_verified:
                ui_annotations.extend(
                    item for item in scanned_annotations
                    if item.get("lineup_group") != "INDISPONIBILI"
                )
            visited += 1

        # The page's own API response carries canonical full names, teams,
        # positions and current quotations, including head coaches.
        rows: list[dict[str, Any]] = []
        for _, status, body in responses:
            if status == 200 and body is not None:
                rows.extend(_flatten_market(body))
        # Collapse repeated full-market/fixture responses before matching
        # surnames; otherwise the same player appears multiple times and valid
        # QUINTETTO/PANCHINA annotations are silently rejected as ambiguous.
        rows = _deduplicate_market_rows(rows)

        # Optional raw JSON evidence capture for schema/identity audits. Only
        # response bodies and query-free URLs are saved; browser credentials,
        # cookies, headers, and query parameters are never written.
        capture_path_raw = os.environ.get("DUNKEST_LINEUPS_API_CAPTURE_PATH", "").strip()
        if capture_path_raw:
            capture_path = Path(capture_path_raw).expanduser()
            capture_path.parent.mkdir(parents=True, exist_ok=True)
            safe_responses = []
            for response_url, status, body in responses:
                parsed_url = urlsplit(response_url)
                safe_responses.append({
                    "url": f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}",
                    "status": status,
                    "body": body,
                })
            capture_path.write_text(
                json.dumps({
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    "response_count": len(safe_responses),
                    "responses": safe_responses,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        context.close()

    coach_names: dict[str, str] = {}
    coach_snapshot = _PROJECT_ROOT / "config" / "dunkest_coaches_2026-27.csv"
    if coach_snapshot.exists():
        with coach_snapshot.open(newline="", encoding="utf-8") as stream:
            for item in csv.DictReader(stream):
                team = str(item.get("team") or "").strip().upper()
                name = str(item.get("player_name") or "").strip()
                if team and name:
                    coach_names[team] = name

    unique_annotations = {
        (
            item["team"], item["role"], item["surname"], item["lineup_group"],
            tuple(item.get("_fixture_teams", ())),
        ): item
        for item in ui_annotations
    }

    annotation_count, _unavailable_count = _apply_lineup_annotations(
        rows, list(unique_annotations.values()), coach_names
    )


    for row in rows:
        row["dunkest_turn"] = turn_number
        # Even if the API or an old market snapshot contains a status-like
        # field, Lineups is not an injury source. Eligibility comes from the
        # separate official /1/injuries scrape only.
        row["status"] = ""
        if str(row.get("lineup_group", "")).strip().upper() == "INDISPONIBILI":
            row["lineup_group"] = ""
            row["starter"] = ""

    player_rows = [row for row in rows if row["role"] != "HC"]
    coaches = [row for row in rows if row["role"] == "HC"]
    player_teams = {row["team"] for row in player_rows}
    coach_teams = {row["team"] for row in coaches}
    scheduled_teams = _teams_in_fixtures(fixture_labels)
    missing_player_teams = scheduled_teams - player_teams
    missing_coach_teams = scheduled_teams - coach_teams
    if failed_fixtures:
        print(
            "ATTENZIONE: lettura lineup incompleta per "
            f"{len(failed_fixtures)}/{len(fixture_labels)} fixture non tutte visitate: "
            + ", ".join(failed_fixtures[:4])
            + (" ..." if len(failed_fixtures) > 4 else ".")
        )
    if failed_lineup_fixtures and turn_number is None:
        print(
            "ATTENZIONE: mercato e calendario possono essere salvati, ma non sono state "
            "convalidate le annotazioni quintetto/panchina per: "
            + ", ".join(sorted(failed_lineup_fixtures))
            + ". Per queste partite non vengono applicate etichette di titolarità incerte."
        )
    # The full-gameweek capture requires the complete 30-team market and every
    # fixture card to be visited. Starter/bench annotations are best-effort in
    # that mode; injury/rest data are captured separately from /1/injuries.
    single_turn_lineup_failure = (
        turn_number is not None
        and (annotation_count == 0 or target_visited != len(target_fixture_labels) or bool(failed_lineup_fixtures))
    )
    full_gameweek_fixture_failure = turn_number is None and visited != len(fixture_labels)
    if (len(player_rows) < min_players or not scheduled_teams
            or missing_player_teams or missing_coach_teams
            or single_turn_lineup_failure or full_gameweek_fixture_failure):
        raise RuntimeError(
            "Lineups non ha restituito un listino completo: "
            f"{len(player_rows)} giocatori / {len(player_teams)} squadre, "
            f"{len(coaches)} coach / {len(coach_teams)} squadre, "
            f"{len(scheduled_teams)} squadre nel calendario visibile "
            f"(senza listino: {sorted(missing_player_teams)}, senza coach: {sorted(missing_coach_teams)}), "
            f"{annotation_count} dati lineup associati, "
            f"{visited}/{len(fixture_labels)} partite lette per il listino, {target_visited}/{len(target_fixture_labels)} "
            f"fixture target {'della giornata' if turn_number is None else f'del TURNO {turn_number}'} verificate; "
            f"coverage lineup non valido: {failed_lineup_fixtures}; "
            f"controlli non raggiunti: {failed_fixtures[:4]}; {first_click_diagnostic}. "
            "Il CSV precedente è rimasto intatto; controlla login e giornata selezionata."
        )

    market_fields = [
        "player_name", "cr", "team", "role", "lineup_group", "starter", "status", "dunkest_turn",
    ]
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=market_fields,
            restval="",
            extrasaction="ignore",
        )
        writer.writeheader()
        ordered = sorted(rows, key=lambda row: (row["role"] == "HC", row["team"], row["player_name"]))
        writer.writerows([{field: row.get(field, "") for field in market_fields} for row in ordered])
    temporary.replace(output)
    # Preserve the complete current Dunkest Giornata fixture list. The coach
    # model needs matchups from later turns too; the selected Turno is only the
    # availability/lineup snapshot for this run.
    fixture_path = output.with_name("lineups_fixtures.csv")
    observed_at = datetime.now(timezone.utc).isoformat()
    fixture_rows = []
    for label in fixture_labels:
        observation = _fixture_observation(
            label,
            fixture_turns.get(label, turn_number),
            observed_at,
            fixture_eligibility,
        )
        if observation is not None:
            fixture_rows.append(observation)
    eligibility_known = sum(
        observation.get(eligible_field) is not None
        for observation in fixture_rows
        for eligible_field in ("team_a_eligible", "team_b_eligible")
    )
    observed_eligible_teams = _eligible_teams_from_fixture_rows(fixture_rows)
    fixture_eligibility_conflicts: list[dict[str, Any]] = []
    fixture_fields = [
        "fixture_label", "team_a", "team_b", "display_day", "display_month",
        "dunkest_turn", "team_a_eligible", "team_b_eligible", "observed_at_utc",
    ]
    if fixture_rows:
        # Keep the unmodified observation for audit. The effective fixture map
        # below may retain a prior positive side flag if the new UI styling
        # would otherwise make a team disappear from an unchanged 30-team slate.
        observation_scope = f"turn{turn_number}" if turn_number is not None else "full_gameweek"
        observation_path = output.with_name(
            f"lineups_fixtures_{observation_scope}_observation.csv"
        )
        observation_tmp = observation_path.with_suffix(".csv.tmp")
        with observation_tmp.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fixture_fields)
            writer.writeheader()
            writer.writerows(fixture_rows)
        observation_tmp.replace(observation_path)

        previous_rows: list[dict[str, Any]] = []
        if fixture_path.exists():
            try:
                with fixture_path.open("r", newline="", encoding="utf-8-sig") as stream:
                    previous_rows = list(csv.DictReader(stream))
            except (OSError, csv.Error):
                previous_rows = []
        effective_rows, fixture_eligibility_conflicts = _retain_previous_verified_fixture_eligibility(
            fixture_rows, previous_rows
        )
        eligible_teams = _eligible_teams_from_fixture_rows(effective_rows)
        if fixture_eligibility_conflicts:
            teams = ", ".join(item["team"] for item in fixture_eligibility_conflicts)
            print(
                "ATTENZIONE: osservazione Lineups in conflitto con la mappatura "
                f"completa precedente per {teams}; conservato il flag positivo "
                "precedentemente verificato. L'osservazione grezza è archiviata."
            )
        if len(eligible_teams) < 30:
            print(
                "ATTENZIONE: il calendario ha verificato un matchup valido per "
                f"{len(eligible_teams)} squadre (osservazione grezza: "
                f"{len(observed_eligible_teams)}) e letto lo stato di {eligibility_known} lati. "
                "La mappatura resta incompleta; non sono state inventate squadre o partite."
            )
        fixture_tmp = fixture_path.with_suffix(".csv.tmp")
        with fixture_tmp.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fixture_fields)
            writer.writeheader()
            writer.writerows(effective_rows)
        fixture_tmp.replace(fixture_path)
    else:
        eligible_teams = set()
    metadata_path = output.with_suffix(output.suffix + ".meta.json")
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    metadata_tmp.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "dunkest_lineups_browser",
                "dunkest_turn": int(turn_number) if turn_number is not None else None,
                "capture_scope": "single_turn" if turn_number is not None else "full_gameweek_all_turns",
                "fixtures_scanned": visited,
                "fixtures_total": len(fixture_labels),
                "fixtures_failed": failed_fixtures,
                "all_fixtures_covered": visited == len(fixture_labels),
                "lineup_fixtures_unverified": sorted(failed_lineup_fixtures),
                "all_eligible_lineups_verified": not failed_lineup_fixtures,
                "target_fixtures_scanned": target_visited,
                "target_fixtures_total": len(target_fixture_labels),
                "target_fixtures_complete": target_visited == len(target_fixture_labels),
                "first_fixture_failure_diagnostic": first_click_diagnostic or None,
                "fixture_observations": len(fixture_rows),
                "fixture_team_statuses_known": eligibility_known,
                "fixture_observed_eligible_teams": len(observed_eligible_teams),
                "fixture_eligible_teams": len(eligible_teams),
                "fixture_eligibility_conflicts": fixture_eligibility_conflicts,
                "fixture_mapping_effective_source": (
                    "previous_complete_mapping_fallback"
                    if fixture_eligibility_conflicts else "current_browser_observation"
                ),
                "players": len(player_rows),
                "coaches": len(coaches),
                "injury_statuses_included": False,
                "injury_source": "separate_official_fantasy_dunkest_injuries_page",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metadata_tmp.replace(metadata_path)
    print(
        f"Listino aggiornato: {len(player_rows)} giocatori, {len(coaches)} coach, "
        f"{len(scheduled_teams)} squadre nel calendario, {annotation_count} annotazioni roster/coach; "
        f"{visited}/{len(fixture_labels)} partite visitate, "
        f"{target_visited}/{len(target_fixture_labels)} fixture target "
        f"({'tutta la giornata' if turn_number is None else f'turno {turn_number}'}; "
        f"{len(failed_lineup_fixtures)} lineup non verificate) in {output}"
    )
    return output


def merge_turn_market_snapshots(snapshot_paths: list[Path], output: Path) -> Path:
    """Merge per-turn captures without discarding other turns' lineup labels."""
    output = output.expanduser().resolve()
    snapshots: list[dict[str, Any]] = []
    for raw_path in snapshot_paths:
        path = Path(raw_path).expanduser().resolve()
        metadata_path = path.with_suffix(path.suffix + ".meta.json")
        if not path.is_file() or not metadata_path.is_file():
            raise RuntimeError(f"Snapshot Lineups incompleto: {path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        try:
            turn = int(metadata["dunkest_turn"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Turno mancante nei metadati Lineups: {metadata_path}") from exc
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        if not fieldnames or not rows:
            raise RuntimeError(f"Snapshot Lineups vuoto: {path}")
        keyed: dict[tuple[str, str, str], dict[str, str]] = {}
        for row in rows:
            key = (player_key(row.get("player_name", "")),
                   str(row.get("team", "")).strip().upper(),
                   str(row.get("role", "")).strip().upper())
            if all(key):
                keyed[key] = row
        snapshots.append({"path": path, "metadata": metadata, "turn": turn,
                          "fieldnames": fieldnames, "rows": rows, "by_key": keyed})

    if not snapshots:
        raise ValueError("Serve almeno uno snapshot Lineups per il merge.")
    turns = [snapshot["turn"] for snapshot in snapshots]
    if len(set(turns)) != len(turns):
        raise ValueError(f"Snapshot Lineups duplicati per turno: {turns}")
    latest = max(snapshots, key=lambda item: str(item["metadata"].get("fetched_at", "")))

    ordered_keys: list[tuple[str, str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for snapshot in [latest, *snapshots]:
        for row in snapshot["rows"]:
            key = (player_key(row.get("player_name", "")),
                   str(row.get("team", "")).strip().upper(),
                   str(row.get("role", "")).strip().upper())
            if all(key) and key not in seen_keys:
                seen_keys.add(key)
                ordered_keys.append(key)

    merged_rows: list[dict[str, str]] = []
    for key in ordered_keys:
        candidates = [(snapshot, snapshot["by_key"][key]) for snapshot in snapshots
                      if key in snapshot["by_key"]]
        base = latest["by_key"].get(key)
        if base is None:
            base = max(candidates, key=lambda item: str(item[0]["metadata"].get("fetched_at", "")))[1]
        row = dict(base)
        # Merge roster annotations only. Legacy per-turn snapshots may contain
        # injury labels from the old Lineups panel; they must not survive a merge.
        annotated = [item for item in candidates
                     if str(item[1].get("lineup_group", "")).strip().upper()
                     in {"QUINTETTO", "PANCHINA", "COACH"}]
        if annotated:
            _, chosen = max(annotated,
                            key=lambda item: str(item[0]["metadata"].get("fetched_at", "")))
            row["lineup_group"] = chosen.get("lineup_group", "")
            row["starter"] = chosen.get("starter", "")
        else:
            row.update(lineup_group="", starter="")
        row["status"] = ""
        # A single-turn scrape writes its scope into every row; it is not the
        # player's actual turn. The fixture bridge assigns that later.
        row["dunkest_turn"] = ""
        for snapshot in snapshots:
            turn = snapshot["turn"]
            turn_row = snapshot["by_key"].get(key, {})
            turn_group = str(turn_row.get("lineup_group", "")).strip().upper()
            if turn_group not in {"QUINTETTO", "PANCHINA", "COACH"}:
                turn_group = ""
            row[f"lineup_group_turn{turn}"] = turn_group
            row[f"starter_turn{turn}"] = turn_row.get("starter", "") if turn_group else ""
            row[f"status_turn{turn}"] = ""
        merged_rows.append(row)

    fieldnames = list(latest["fieldnames"])
    for field in (
        "lineup_group", "starter", "status", "dunkest_turn",
        *(f"{column}_turn{turn}" for turn in (1, 2, 3)
          for column in ("lineup_group", "starter", "status")),
    ):
        if field not in fieldnames:
            fieldnames.append(field)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged_rows)
    temporary.replace(output)

    groups: dict[str, int] = {}
    for row in merged_rows:
        group = str(row.get("lineup_group", "")).strip().upper()
        if group:
            groups[group] = groups.get(group, 0) + 1
    per_turn = [{"turn": item["turn"], "fetched_at": item["metadata"].get("fetched_at"),
                 "target_fixtures_scanned": item["metadata"].get("target_fixtures_scanned"),
                 "target_fixtures_total": item["metadata"].get("target_fixtures_total"),
                 "target_fixtures_complete": item["metadata"].get("target_fixtures_complete")}
                for item in sorted(snapshots, key=lambda item: item["turn"])]
    metadata_out = dict(latest["metadata"])
    metadata_out.update({
        "source": "dunkest_lineups_browser",
        "capture_scope": "full_gameweek_all_turns_merged",
        "dunkest_turn": None,
        "turns_captured": sorted(turns),
        "turn_captures": per_turn,
        "fixtures_failed": sorted({str(f) for item in snapshots
                                   for f in item["metadata"].get("fixtures_failed", [])}),
        "all_fixtures_covered": all(bool(item["metadata"].get("all_fixtures_covered"))
                                    for item in snapshots),
        "target_fixtures_scanned": sum(int(item["metadata"].get("target_fixtures_scanned", 0) or 0)
                                       for item in snapshots),
        "target_fixtures_total": sum(int(item["metadata"].get("target_fixtures_total", 0) or 0)
                                     for item in snapshots),
        "target_fixtures_complete": all(bool(item["metadata"].get("target_fixtures_complete"))
                                        for item in snapshots),
        "players": sum(str(row.get("role", "")).upper() != "HC" for row in merged_rows),
        "coaches": sum(str(row.get("role", "")).upper() == "HC" for row in merged_rows),
        "lineup_group_counts": groups,
        "injury_statuses_included": False,
        "injury_source": "separate_official_fantasy_dunkest_injuries_page",
    })
    metadata_path = output.with_suffix(output.suffix + ".meta.json")
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    metadata_tmp.write_text(json.dumps(metadata_out, indent=2), encoding="utf-8")
    metadata_tmp.replace(metadata_path)
    print(f"Merge Lineups completato: {metadata_out['players']} giocatori, "
          f"{metadata_out['coaches']} coach, turni {sorted(turns)}, gruppi {groups}")
    return output


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "data" / "current_lineups_market.csv"
    scrape_lineups_market(destination, turn_number=1)


if __name__ == "__main__":
    main()
