from __future__ import annotations

import csv
import io
import json
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
    if (
        re.search(r"\b(?:ADVERTISEMENT|ADVERTISING|LEGENDA|PUNTEGGI|INDISPONIBILI)\b", text, re.I)
        or re.search(r"\b\d{1,2}/\d{1,2}\b", text)
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
    name = " ".join(name.split()).strip(" -")
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
    headings = []
    for node in items:
        label = " ".join(str(node.get("label", "")).upper().split())
        section_heading = re.search(r"\b(QUINTETTO|PANCHINA|INDISPONIBILI)\b", label)
        if section_heading:
            headings.append((float(node.get("y", 0)), section_heading.group(1)))
    headings.sort()

    annotations: list[dict[str, Any]] = []
    starter_count = {home: 0, away: 0}
    section_active = unavailable_section_active
    for node in items:
        label = str(node.get("label", ""))
        y = float(node.get("y", 0))
        team = home if float(node.get("x", 0)) < width / 2 else away
        prior_headers = [header for top, header in headings if top <= y + 2]
        if not prior_headers:
            if re.search(r"\bHC\b", label, re.I):
                section = "COACH"
            elif re.search(r"\d+(?:[,.]\d+)?\s*cr\b", label, re.I):
                section = "QUINTETTO" if starter_count[team] < 5 else "PANCHINA"
                starter_count[team] += 1
            elif section_active:
                section = "INDISPONIBILI"
            else:
                continue
        else:
            section = prior_headers[-1]
            section_active = section == "INDISPONIBILI"
            if section == "INDISPONIBILI" and re.search(r"\bHC\b", label, re.I):
                continue
        if re.fullmatch(r"\s*(?:QUINTETTO|PANCHINA|INDISPONIBILI)(?:\s*\(\d+\))?\s*", label, re.I):
            continue
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


def _scroll_collect_unavailable(page, fixture_label: str, *, max_steps: int = 60) -> list[dict[str, Any]]:
    """Use real page scrolling to the matchup end; collect roster, coach, and OUT rows."""
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    stalled = 0
    unavailable_section_active = False
    page.mouse.move(0.5 * page.viewport_size["width"], 0.8 * page.viewport_size["height"])
    for _ in range(max_steps):
        # Collect before scrolling as the first lineup rows can be above the
        # fold. Scroll via real wheel/PageDown events so Flutter's own vertical
        # scroll controller receives the input; do not move unrelated panes.
        annotations, unavailable_section_active = _collect_lineup_annotations_state(
            page, fixture_label, unavailable_section_active=unavailable_section_active
        )
        for annotation in annotations:
            key = (annotation["team"], annotation["role"], annotation["surname"], annotation["lineup_group"])
            found[key] = annotation
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
        for annotation in annotations:
            key = (annotation["team"], annotation["role"], annotation["surname"], annotation["lineup_group"])
            found[key] = annotation
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
                for annotation in annotations:
                    key = (annotation["team"], annotation["role"], annotation["surname"], annotation["lineup_group"])
                    found[key] = annotation
                break
    # Return the document viewport to the schedule without resetting carousel
    # offsets or hidden nested views. The next fixture can then be located.
    if not any(item["lineup_group"] == "INDISPONIBILI" for item in found.values()):
        ocr_annotations, _ = _ocr_unavailable_panel(page)
        for annotation in ocr_annotations:
            key = (annotation["team"], annotation["role"], annotation["surname"], annotation["lineup_group"])
            found[key] = annotation
    page.keyboard.press("Home")
    page.mouse.wheel(0, -12000)
    page.wait_for_timeout(180)
    return list(found.values())


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
    turn_number: int,
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
        "dunkest_turn": int(turn_number),
        "observed_at_utc": str(observed_at_utc),
    }


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
    batches: list[list[dict[str, Any]]], turn_number: int
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
            if active_week == turn_number and label not in target_fixtures:
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
    return page.evaluate("""() => {
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
          const teams = [...label.toUpperCase().matchAll(/\\b([A-Z]{3})\\s+(?:VS|@)\\s+([A-Z]{3})\\b/g)]
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


def _scan_fixture_list(page, turn_number: int, *, max_steps: int = 80) -> tuple[list[str], list[str], dict[str, int], dict[str, dict[str, bool | None]]]:
    """Progressively scroll the fixture list to load every lazy Flutter row."""
    batches: list[list[dict[str, Any]]] = []
    eligibility_by_fixture: dict[str, dict[str, bool | None]] = {}
    stalled = 0
    seen_labels: set[str] = set()
    for _ in range(max_steps):
        nodes = _fixture_nodes(page)
        if nodes:
            batches.append(nodes)
            seen_labels.update(" ".join(str(item.get("label", "")).split()) for item in nodes)
            screenshot_status = _fixture_statuses_from_screenshot(page, nodes)
            for item in nodes:
                label = " ".join(str(item.get("label", "")).split())
                match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", label, re.I)
                if not match:
                    continue
                teams = (match.group(1).upper(), match.group(2).upper())
                styles = item.get("team_styles") or {}
                statuses = eligibility_by_fixture.setdefault(
                    _fixture_status_key(label),
                    eligibility_by_fixture.get(_fixture_pair_key(label), {}),
                )
                observed = screenshot_status.get(_fixture_status_key(label)) or screenshot_status.get(
                    _fixture_pair_key(label), {}
                )
                for team in teams:
                    status = observed.get(team)
                    if status is not None or team not in statuses:
                        statuses[team] = status
                eligibility_by_fixture[_fixture_pair_key(label)] = statuses
        moved = page.evaluate("""() => {
          const roots = [document.scrollingElement], pending = [document];
          while (pending.length) {
            const root = pending.pop();
            for (const el of root.querySelectorAll('*')) {
              roots.push(el);
              if (el.shadowRoot) pending.push(el.shadowRoot);
            }
          }
          let moved = false;
          for (const el of roots) {
            if (!el || el.scrollHeight <= el.clientHeight + 8) continue;
            const before = el.scrollTop;
            const step = Math.max(260, Math.floor(el.clientHeight * 0.72));
            el.scrollTop = Math.min(el.scrollHeight - el.clientHeight, before + step);
            if (el.scrollTop > before + 1) moved = true;
          }
          return moved;
        }""")
        page.wait_for_timeout(180)
        if moved:
            stalled = 0
        else:
            page.mouse.wheel(0, 620)
            page.keyboard.press("PageDown")
            page.wait_for_timeout(180)
            fallback_nodes = _fixture_nodes(page)
            if fallback_nodes:
                batches.append(fallback_nodes)
                screenshot_status = _fixture_statuses_from_screenshot(page, fallback_nodes)
                for item in fallback_nodes:
                    label = " ".join(str(item.get("label", "")).split())
                    match = re.search(r"\b([A-Z]{3})\s+(?:VS|@)\s+([A-Z]{3})\b", label, re.I)
                    if not match:
                        continue
                    teams = (match.group(1).upper(), match.group(2).upper())
                    styles = item.get("team_styles") or {}
                    statuses = eligibility_by_fixture.setdefault(
                        _fixture_status_key(label),
                        eligibility_by_fixture.get(_fixture_pair_key(label), {}),
                    )
                    observed = screenshot_status.get(_fixture_status_key(label)) or screenshot_status.get(
                        _fixture_pair_key(label), {}
                    )
                    for team in teams:
                        status = observed.get(team)
                        if status is not None or team not in statuses:
                            statuses[team] = status
                    eligibility_by_fixture[_fixture_pair_key(label)] = statuses
            new_labels = {
                " ".join(str(item.get("label", "")).split()) for item in fallback_nodes
            } - seen_labels
            seen_labels.update(new_labels)
            stalled = 0 if new_labels else stalled + 1
        if stalled >= 2:
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
    brightnesses.sort()
    return float(brightnesses[len(brightnesses) // 2])


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
            token = re.sub(r"[^A-Z]", "", str(row.get("text", "")).upper())
            if token not in TEAM_CODES:
                continue
            try:
                x, y = int(row["left"]), int(row["top"])
                w, h = int(row["width"]), int(row["height"])
            except (KeyError, TypeError, ValueError):
                continue
            luminance = _visible_word_luminance(pixels, (x, y, x + w, y + h))
            status = True if luminance is not None and luminance <= 90 else (
                False if luminance is not None and luminance >= 125 else None
            )
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
            for team in (first, second):
                nearby = [word for word in words if word["team"] == team and left <= word["x"] <= right]
                if not nearby:
                    nearby = [word for word in words if word["team"] == team]
                if nearby:
                    chosen = min(nearby, key=lambda word: abs(word["y"] - center_y))
                    if abs(chosen["y"] - center_y) <= max(45.0, float(item.get("bottom", 0) - item.get("top", 0)) * scale):
                        entry[team] = chosen["status"]
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
    moved = page.evaluate("""() => {
      const roots = [document], pending = [document], controls = [], candidates = new Map();
      const game = /\\b[A-Z]{3}\\s+(?:VS|@)\\s+[A-Z]{3}\\b/i;
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
      const ordered = [...candidates.entries()].sort((a, b) => b[1] - a[1]);
      for (const [el] of ordered) {
        const maxY = el.scrollHeight - el.clientHeight;
        if (maxY > 8 && el.scrollTop < maxY - 2) {
          const before = el.scrollTop;
          el.scrollTop = Math.min(maxY, before + Math.max(220, Math.floor(el.clientHeight * 0.6)));
          if (el.scrollTop > before + 1) return true;
        }
        const maxX = el.scrollWidth - el.clientWidth;
        if (maxX > 8 && el.scrollLeft < maxX - 2) {
          const before = el.scrollLeft;
          el.scrollLeft = Math.min(maxX, before + Math.max(220, Math.floor(el.clientWidth * 0.6)));
          if (el.scrollLeft > before + 1) return true;
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
                chosen = button_candidates[0]
                if date:
                    for candidate in button_candidates:
                        name = candidate.inner_text(timeout=250)
                        if date.group(0) in name:
                            chosen = candidate
                            break
                chosen.click(force=True, timeout=2500)
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
                control.click(force=True, timeout=1500)
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
              const choices = (dated.length ? dated : nodes).sort((a, b) => a.priority - b.priority);
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
                found.push({tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '',
                  label: label.slice(0, 90), width: Math.round(rect.width), height: Math.round(rect.height)});
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

    # Role from the injury panel is often missing or wrong; never require it.
    # Prefer same role only as a soft disambiguation signal later.
    pool = [row for row in rows if row.get("role") != "HC"]

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
        # The two visual columns can be reversed relative to the fixture label.
        if not candidates and role == "ANY":
            candidates = [
                row for row in rows
                if row["role"] != "HC"
                and player_surname(row["player_name"]) == player_surname(surname or ui_name)
            ]
        elif not candidates and role != "HC":
            candidates = [
                row for row in rows
                if row["role"] == role
                and player_surname(row["player_name"]) == player_surname(surname or ui_name)
            ]
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
                rows.append({"player_name": name, "cr": cr, "team": team, "role": role})

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


def scrape_lineups_market(output: Path, *, turn_number: int = 1, min_players: int = 250) -> Path:
    """Open Dunkest Lineups and refresh the live CR CSV.

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
        print("Si è aperta Dunkest Lineups in una finestra temporanea.")
        print("Accedi nel browser e torna alla pagina Lineups. Non inserire credenziali nel terminale.")
        input("Quando visualizzi le partite, premi Invio qui per aggiornare il listino: ")

        # Recheck after navigation/login: Flutter may recreate its semantics
        # overlay when the route changes.
        _enable_flutter_accessibility(page)
        page.wait_for_timeout(1200)
        fixture_labels, target_fixture_labels, fixture_turns, fixture_eligibility = _scan_fixture_list(page, turn_number)

        if not target_fixture_labels:
            diagnostic = _page_diagnostic(page, responses)
            context.close()
            raise RuntimeError(
                f"Non trovo le partite del TURNO {turn_number} nella pagina Lineups. "
                "Verifica che la pagina "
                "mostri gli incontri e che l'accessibilità sia attiva. Diagnostica: " + diagnostic
            )

        visited = 0
        target_visited = 0
        failed_fixtures: list[str] = []
        first_click_diagnostic = ""
        _reset_scrollables(page)
        for label in fixture_labels:
            already_selected = visited == 0 and _fixture_present_in_market_response(responses, label)
            loaded = already_selected
            for attempt in range(3):
                if loaded:
                    break
                response_start = len(responses)
                clicked = _click_fixture(page, label)
                if clicked:
                    loaded = _wait_for_fixture_market(
                        page, responses, label, start=response_start
                    )
                if not loaded and attempt < 2:
                    page.wait_for_timeout(300)
            if not loaded:
                failed_fixtures.append(label)
                if not first_click_diagnostic:
                    first_click_diagnostic = _fixture_click_diagnostic(page, label)
                continue
            if already_selected:
                print(f"Partita già selezionata all'apertura: {label}")
            is_target_fixture = label in target_fixture_labels
            if is_target_fixture:
                target_visited += 1
            # Scroll each selected matchup from its lineup through the bottom
            # of the page. This captures lineup/coach rows and the optional
            # unavailable panel before moving to the next matchup.
            scanned_annotations = _scroll_collect_unavailable(page, label)
            # Starters, bench, and coach belong to the selected round's
            # fixtures only. The unavailable panel is league-wide on some
            # page builds, so merge its OUT entries while scanning every card.
            ui_annotations.extend(
                item for item in scanned_annotations
                if is_target_fixture or item["lineup_group"] == "INDISPONIBILI"
            )
            visited += 1
            # Keep the Flutter schedule's own scroll position. Resetting it
            # after each game can detach earlier virtualized fixture controls;
            # the next click advances from the current carousel position.

        # The page's own API response carries canonical full names, teams,
        # positions and current quotations, including head coaches.
        rows: list[dict[str, Any]] = []
        for _, status, body in responses:
            if status == 200 and body is not None:
                rows.extend(_flatten_market(body))
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
        (item["team"], item["role"], item["surname"], item["lineup_group"]): item
        for item in ui_annotations
    }
    unavailable_found = sum(
        item["lineup_group"] == "INDISPONIBILI" for item in unique_annotations.values()
    )
    annotation_count, unavailable_count = _apply_lineup_annotations(
        rows, list(unique_annotations.values()), coach_names
    )
    if unavailable_found and unavailable_count == 0:
        print(
            "ATTENZIONE: il pannello mostra indisponibili, ma nessuno è stato abbinato "
            "al listino corrente; verifica i nomi/team prima di usare queste assenze."
        )

    for row in rows:
        row["dunkest_turn"] = turn_number

    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        by_identity[(row["team"], row["role"], row["player_name"].casefold())] = row
    rows = list(by_identity.values())
    player_rows = [row for row in rows if row["role"] != "HC"]
    coaches = [row for row in rows if row["role"] == "HC"]
    player_teams = {row["team"] for row in player_rows}
    coach_teams = {row["team"] for row in coaches}
    scheduled_teams = _teams_in_fixtures(fixture_labels)
    missing_player_teams = scheduled_teams - player_teams
    missing_coach_teams = scheduled_teams - coach_teams
    if (len(player_rows) < min_players or not scheduled_teams
            or missing_player_teams or missing_coach_teams
            or annotation_count == 0 or visited != len(fixture_labels)
            or target_visited != len(target_fixture_labels)):
        raise RuntimeError(
            "Lineups non ha restituito un listino completo: "
            f"{len(player_rows)} giocatori / {len(player_teams)} squadre, "
            f"{len(coaches)} coach / {len(coach_teams)} squadre, "
            f"{len(scheduled_teams)} squadre nel calendario visibile "
            f"(senza listino: {sorted(missing_player_teams)}, senza coach: {sorted(missing_coach_teams)}), "
            f"{annotation_count} dati lineup associati ({unavailable_found} indisponibili letti, "
            f"{unavailable_count} associati), "
            f"{visited}/{len(fixture_labels)} partite lette per il listino, {target_visited} del TURNO {turn_number}; "
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
    eligible_teams = {
        str(observation.get(team_field, "")).upper()
        for observation in fixture_rows
        for team_field, eligible_field in (
            ("team_a", "team_a_eligible"),
            ("team_b", "team_b_eligible"),
        )
        if observation.get(eligible_field) is True
    }
    if len(eligible_teams) < 30:
        print(
            "ATTENZIONE: il calendario ha verificato un matchup valido per "
            f"{len(eligible_teams)} squadre e letto lo stato di {eligibility_known} lati. "
            "Le squadre a riposo non sono ricostruite per supposizione; solo i "
            "matchup con stato Dunkest leggibile saranno usati."
        )
    if fixture_rows:
        fixture_fields = [
            "fixture_label", "team_a", "team_b", "display_day", "display_month",
            "dunkest_turn", "team_a_eligible", "team_b_eligible", "observed_at_utc",
        ]
        fixture_tmp = fixture_path.with_suffix(".csv.tmp")
        with fixture_tmp.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fixture_fields)
            writer.writeheader()
            writer.writerows(fixture_rows)
        fixture_tmp.replace(fixture_path)
    metadata_path = output.with_suffix(output.suffix + ".meta.json")
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    metadata_tmp.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "dunkest_lineups_browser",
                "dunkest_turn": int(turn_number),
                "fixtures_scanned": visited,
                "target_fixtures_scanned": target_visited,
                "fixture_observations": len(fixture_rows),
                "fixture_team_statuses_known": eligibility_known,
                "fixture_eligible_teams": len(eligible_teams),
                "players": len(player_rows),
                "coaches": len(coaches),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metadata_tmp.replace(metadata_path)
    # Store observed Lineups status by Turno; it is not a Giornata mapping.
    availability_path = output.with_name("lineups_availability.csv")
    unavailable_rows = []
    for row in rows:
        if str(row.get("status") or "").upper() != "OUT" or row.get("role") == "HC":
            continue
        unavailable_rows.append({
            "player_name": row["player_name"],
            "team": row["team"],
            "status": "OUT",
            "dunkest_turn": turn_number,
        })
    # Keep unmatched INDISPONIBILI labels so eligibility can still exclude by
    # surname/team even when the Flutter string did not resolve to a market row.
    matched_out_keys = {
        (row["player_name"].casefold(), str(row["team"]).upper())
        for row in unavailable_rows
    }
    for annotation in unique_annotations.values():
        if annotation.get("lineup_group") != "INDISPONIBILI":
            continue
        ui_name = str(annotation.get("ui_name") or annotation.get("surname") or "").strip()
        team = str(annotation.get("team") or "").strip().upper()
        if not ui_name or not team:
            continue
        key = (ui_name.casefold(), team)
        if key in matched_out_keys:
            continue
        # Prefer the already-matched market row if a later pass resolved it.
        resolved = _match_unavailable_to_market(annotation, rows)
        if resolved is not None:
            resolved_key = (
                str(resolved["player_name"]).casefold(),
                str(resolved["team"]).upper(),
            )
            if resolved_key not in matched_out_keys:
                resolved["status"] = "OUT"
                resolved["lineup_group"] = "INDISPONIBILI"
                unavailable_rows.append({
                    "player_name": resolved["player_name"],
                    "team": resolved["team"],
                    "status": "OUT",
                    "dunkest_turn": turn_number,
                })
                matched_out_keys.add(resolved_key)
            continue
        unavailable_rows.append({
            "player_name": ui_name.title() if ui_name.islower() else ui_name,
            "team": team,
            "status": "OUT",
            "dunkest_turn": turn_number,
        })
        matched_out_keys.add(key)
    unavailable_rows = list({(row["player_name"].casefold(), row["team"]): row
                             for row in unavailable_rows}.values())
    availability_fields = ["player_name", "team", "status", "dunkest_turn"]
    previous = []
    if availability_path.exists():
        with availability_path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                # Legacy files used "gameweek" for the Turno number; migrate in place.
                turn_value = row.get("dunkest_turn")
                if turn_value is None or str(turn_value).strip() == "":
                    turn_value = row.get("gameweek")
                if str(turn_value) == str(turn_number):
                    continue
                previous.append({
                    "player_name": row.get("player_name", ""),
                    "team": row.get("team", ""),
                    "status": row.get("status", ""),
                    "dunkest_turn": turn_value,
                })
    archive_tmp = availability_path.with_suffix(".csv.tmp")
    with archive_tmp.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=availability_fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(previous + unavailable_rows)
    archive_tmp.replace(availability_path)
    print(
        f"Listino aggiornato: {len(player_rows)} giocatori, {len(coaches)} coach, "
        f"{len(scheduled_teams)} squadre nel calendario, "
        f"{annotation_count} indicazioni lineup ({unavailable_found} indisponibili letti, "
        f"{len(unavailable_rows)} archiviati, {unavailable_count} OUT abbinati al listino; "
        f"{visited} partite scansionate in fondo, {target_visited} del turno selezionato) in {output}"
    )
    return output


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "data" / "current_lineups_market.csv"
    scrape_lineups_market(destination, turn_number=1)


if __name__ == "__main__":
    main()
