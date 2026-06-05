import json
from pathlib import Path

from tools.reports.build_testnet_ready_package import build_testnet_ready_report


def test_build_testnet_ready_report_writes_required_sections(tmp_path: Path) -> None:
    oos_path = tmp_path / "oos.json"
    parity_path = tmp_path / "parity.json"
    cfg_path = tmp_path / "config_snapshot.json"
    oos_path.write_text(json.dumps({"surfaces": 2, "stable": True}), encoding="utf-8")
    parity_path.write_text(json.dumps({"threshold_provenance_retained": True}), encoding="utf-8")
    cfg_path.write_text("{}", encoding="utf-8")
    out_path = tmp_path / "TESTNET_READY_PACKAGE_V1.md"

    build_testnet_ready_report(
        oos_report_path=str(oos_path),
        parity_summary_path=str(parity_path),
        config_snapshot_path=str(cfg_path),
        output_path=str(out_path),
    )

    text = out_path.read_text(encoding="utf-8")
    assert "## Halt Conditions" in text
    assert "## Rollback Conditions" in text
    assert "testnet-ready only" in text
