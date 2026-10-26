import json
import subprocess

from dunkest import __main__ as cli


class ConsoleCapture:
    def __init__(self):
        self.messages = []

    def print(self, message):
        self.messages.append(str(message))


def test_run_archive_integration_preserves_ineligible_status(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    archive_dir = tmp_path / "archives" / "run"
    responses = [
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "archived",
                    "archive_path": str(archive_dir),
                    "pre_lock_eligible": False,
                    "eligibility_status": "incomplete_evidence",
                }
            ),
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "incomplete",
                    "rechecked_pre_lock_eligible": False,
                }
            ),
            stderr="",
        ),
    ]
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = cli._archive_and_review_run(run_dir, tmp_path / "data")

    assert result["status"] == "reviewed"
    assert result["archive"]["pre_lock_eligible"] is False
    assert result["review"]["rechecked_pre_lock_eligible"] is False
    assert len(calls) == 2
    assert "archive_dunkest_pre_lock_run_v1.py" in calls[0][0][1]
    assert str(tmp_path / "data" / "archives" / "pre_lock") in calls[0][0]
    assert "review_dunkest_pre_lock_archive_v1.py" in calls[1][0][1]
    assert str(archive_dir) in calls[1][0]


def test_run_archive_integration_reports_archive_failure_without_review(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(args=command, returncode=2, stdout="", stderr="missing stable IDs")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = cli._archive_and_review_run(tmp_path / "run", tmp_path / "data")

    assert result == {"status": "archive_failed", "error": "missing stable IDs"}


def test_archive_review_reporting_distinguishes_eligible_diagnostic_and_technical_failure(monkeypatch):
    console = ConsoleCapture()
    monkeypatch.setattr(cli, "CONSOLE", console)

    cli._report_archive_review(
        {
            "status": "reviewed",
            "archive": {"pre_lock_eligible": True, "archive_path": "/archive/eligible"},
            "review": {"rechecked_pre_lock_eligible": True, "status": "verified_pre_lock"},
        }
    )
    assert "Bundle pre-lock verificato" in console.messages[-1]

    cli._report_archive_review(
        {
            "status": "reviewed",
            "archive": {
                "pre_lock_eligible": False,
                "eligibility_status": "incomplete_evidence",
                "archive_path": "/archive/diagnostic",
            },
            "review": {"rechecked_pre_lock_eligible": False, "status": "incomplete"},
        }
    )
    assert "non eleggibile" in console.messages[-1]
    assert "diagnostic" in console.messages[-1]

    try:
        cli._report_archive_review({"status": "archive_failed", "error": "missing stable IDs"})
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("technical archive failure must return a nonzero CLI status")
    assert "non va considerato eleggibile" in console.messages[-1]
