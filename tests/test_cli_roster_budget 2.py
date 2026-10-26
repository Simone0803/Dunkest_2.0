from __future__ import annotations

import sys

import pytest

from dunkest.__main__ import main
from dunkest.config import Settings


def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "from_yaml", classmethod(lambda cls, path=None: Settings()))


def test_run_after_gameweek_one_uses_budget_from_roster(
    monkeypatch, tmp_path
):
    import pandas as pd
    import dunkest.__main__ as cli
    from dunkest.data.dunkest import fixtures, lineups_browser

    settings = Settings(data_dir=str(tmp_path))
    roster_path = tmp_path / "current_roster.yaml"
    roster_path.write_text(
        "budget: 96.1\nplayers:\n"
        + "".join(f"  - Player {i}\n" for i in range(10))
        + "coach: Coach\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        Settings, "from_yaml",
        classmethod(lambda cls, path=None: settings),
    )
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        sys, "argv",
        ["dunkest", "run", "--giornata", "2",
         "--roster", str(roster_path)],
    )

    monkeypatch.setattr(
        lineups_browser, "scrape_lineups_market",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        fixtures, "save_current_capture_fixture_mapping",
        lambda *args, **kwargs: pd.DataFrame([{"verified": True}]),
    )

    class StopBeforeTraining(Exception):
        pass

    def stop_before_training(received_settings):
        assert received_settings.budget == 96.1
        assert len(received_settings.current_roster) == 10
        raise StopBeforeTraining

    monkeypatch.setattr(cli, "run_train", stop_before_training)

    with pytest.raises(StopBeforeTraining):
        main()


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
