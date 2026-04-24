from pathlib import Path


def test_task32_decision_making_has_no_hardcoded_mr_imports() -> None:
    dm_path = Path("apps/reference/domains/decision_making/core/facade.py")
    src = dm_path.read_text(encoding="utf-8")

    forbidden = [
        "mean_reversion",
        "MeanReversionHandler",
        "EVT:MR_SIGNAL_PRODUCED",
        "_on_mr_signal_gateway",
        "_on_tick_for_mr",
    ]
    for token in forbidden:
        assert token not in src, f"Found forbidden token {token!r} in {dm_path}"
