from pathlib import Path


def test_no_max_risk_score_null_in_active_config_files():
    """
    MR-RISK-GATE-NONE-FIX-01: "inherit" is key omission, never `max_risk_score: null`.
    """
    cfg_dir = Path("config/aurora")
    for path in sorted(cfg_dir.rglob("*.yaml")):
        if "archive" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "max_risk_score: null" not in text, f"Forbidden null sentinel in {path}"

