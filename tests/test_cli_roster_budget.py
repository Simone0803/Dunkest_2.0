from __future__ import annotations

import sys

import pytest

from dunkest.__main__ import main
from dunkest.config import Settings


def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "from_yaml", classmethod(lambda cls, path=None: Settings()))


def test_run_after_gameweek_one_requires_explicit_budget(monkeypatch, capsys):
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dunkest", "run", "--giornata", "2", "--roster", "config/current_roster.yaml"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert "--budget" in capsys.readouterr().err


@pytest.mark.parametrize("budget", ["0", "-1", "nan", "inf"])
def test_run_rejects_invalid_explicit_budget_after_gameweek_one(monkeypatch, capsys, budget):
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dunkest",
            "run",
            "--giornata",
            "2",
            "--roster",
            "config/current_roster.yaml",
            "--budget",
            budget,
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert "--budget" in capsys.readouterr().err


def test_run_after_gameweek_one_requires_current_roster(monkeypatch, capsys):
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dunkest", "run", "--giornata", "2", "--budget", "97.5"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert "--roster" in capsys.readouterr().err
