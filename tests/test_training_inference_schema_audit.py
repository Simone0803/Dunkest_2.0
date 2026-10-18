from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "training_inference_schema_audit",
    ROOT / "scripts" / "audit_dunkest_training_inference_schema_20261018_v1.py",
)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


def test_schema_audit_refuses_existing_versioned_output_before_loading_data(
    tmp_path, monkeypatch
):
    output = tmp_path / "reports" / "audit"
    output.mkdir(parents=True)
    existing = output / "schema_v1.json"
    existing.write_text("keep-this", encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["schema-audit", "--output-stem", "schema_v1"])

    with pytest.raises(SystemExit, match="Refusing to overwrite versioned output"):
        audit.main()

    assert existing.read_text(encoding="utf-8") == "keep-this"
    assert list(output.iterdir()) == [existing]
