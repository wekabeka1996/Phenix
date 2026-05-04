import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "build_project_atlas.py"
OUT_DIR = REPO_ROOT / "reports" / "atlas"


def test_build_project_atlas_runs_and_writes_reports(tmp_path):
    # Run the script
    proc = subprocess.run([sys.executable, str(SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, f"Script failed: {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

    # Check outputs
    files = [OUT_DIR / "extracted_configs.json", OUT_DIR / "extracted_contracts.json", OUT_DIR / "extracted_events.json", OUT_DIR / "instruments_table.json", OUT_DIR / "gates_policies.json"]
    for f in files:
        assert f.exists(), f"Missing report: {f}"
        # ensure valid json
        with f.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            assert data is not None

    # docs
    doc = REPO_ROOT / "docs" / "PROJECT_ATLAS.md"
    assert doc.exists()
    content = doc.read_text(encoding="utf-8")
    # basic sections
    assert "Instruments" in content
    assert "Gates & Policies" in content
    assert "Events and Contracts" in content

    # diagrams exist and are non-empty
    diagrams = [REPO_ROOT / "docs" / "diagrams" / "events_flow.mmd", REPO_ROOT / "docs" / "diagrams" / "order_lifecycle.mmd", REPO_ROOT / "docs" / "diagrams" / "guards.mmd"]
    for d in diagrams:
        assert d.exists(), f"Missing diagram: {d}"
        assert d.stat().st_size > 20
