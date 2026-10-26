from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

from dunkest.__main__ import main
from dunkest.config import Settings


def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "from_yaml", classmethod(lambda cls, path=None: Settings()))


def test_run_after_gameweek_one_uses_budget_from_roster(monkeypatch, tmp_path):
    import dunkest.__main__ as cli
    from dunkest.data.dunkest import fixtures, lineups_browser

    settings = Settings(data_dir=str(tmp_path))
    monkeypatch.setattr(
        Settings, "from_yaml", classmethod(lambda cls, path=None: settings)
    )
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    roster = tmp_path / "current_roster.yaml"
    roster.write_text(
        "budget: 96.1\nplayers:\n" + "".join(f"  - Player {i}\n" for i in range(10)) + "coach: Coach\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["dunkest", "run", "--giornata", "2", "--roster", str(roster)],
    )
    monkeypatch.setattr(lineups_browser, "scrape_lineups_market", lambda *a, **k: None)
    monkeypatch.setattr(
        fixtures, "save_current_capture_fixture_mapping",
        lambda *a, **k: pd.DataFrame([{"verified": True}]),
    )

    class StopBeforeTraining(Exception):
        pass

    def stop_before_training(received):
        assert received.budget == 96.1
        assert len(received.current_roster) == 10
        capture = tmp_path / "lineups_gw2_capture.json"
        assert json.loads(capture.read_text())["fixture_mapping_verified"] is True
        raise StopBeforeTraining

    monkeypatch.setattr(cli, "run_train", stop_before_training)

    with pytest.raises(StopBeforeTraining):
        main()


def test_failed_fixture_validation_preserves_previous_market_and_does_not_mark_capture_complete(
    monkeypatch, tmp_path, capsys
):
    import dunkest.__main__ as cli
    from dunkest.data.dunkest import fixtures, lineups_browser

    settings = Settings(data_dir=str(tmp_path))
    monkeypatch.setattr(Settings, "from_yaml", classmethod(lambda cls, path=None: settings))
    roster = tmp_path / "current_roster.yaml"
    roster.write_text(
        "budget: 96.1\nplayers:\n" + "".join(f"  - Player {i}\n" for i in range(10)) + "coach: Coach\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["dunkest", "run", "--giornata", "2", "--roster", str(roster)])
    market_path = tmp_path / "current_lineups_market.csv"
    previous_bytes = b"previous verified market\n"
    market_path.write_bytes(previous_bytes)
    metadata_path = market_path.with_suffix(market_path.suffix + ".meta.json")
    previous_metadata = b'{"all_fixtures_covered": true}\n'
    metadata_path.write_bytes(previous_metadata)

    def write_failed_capture(path, **kwargs):
        path.write_bytes(b"stale or incomplete market\n")
        return path

    monkeypatch.setattr(lineups_browser, "scrape_lineups_market", write_failed_capture)
    monkeypatch.setattr(
        fixtures, "save_current_capture_fixture_mapping",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stale gameweek mapping")),
    )
    with pytest.raises(SystemExit):
        main()

    assert market_path.read_bytes() == previous_bytes
    assert metadata_path.read_bytes() == previous_metadata
    assert not (tmp_path / "lineups_gw2_capture.json").exists()
    assert "stale gameweek mapping" in capsys.readouterr().err


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
