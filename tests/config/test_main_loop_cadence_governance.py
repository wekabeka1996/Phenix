"""T4D Timer Governance: main runtime loop cadence (_MAIN_LOOP_CADENCE_SEC).

Classification: MAIN_LOOP_PERIODIC_CALLBACK_GRANULARITY
Governance outcome: KEEP_HARDCODED_WITH_GOVERNANCE_TEST

The main runtime loop in apps/reference/main.py runs two periodic callbacks:
  1. _perform_alert_checks()   — gated by alert_check_interval (60s from observability.yaml)
  2. decision_making.handle_tick() — internally gated at 60s (domain status emitter only)

Trading decisions are event-driven via WebSocket (EVT:BAR_CLOSED) and are NOT
driven by this loop.  The 1s cadence sets the granularity floor for timestamp
comparisons inside the loop.  It is infrastructure, not operator policy, and
must NOT be extracted to YAML.

These tests enforce:
1. _MAIN_LOOP_CADENCE_SEC == 1 (value pinned).
2. The bare literal time.sleep(1) is absent from the main loop section (named
   constant is used).
3. Main loop cadence differs from the alert check interval (semantic separation).
4. No YAML key main_loop_cadence_sec was introduced in any config file.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "apps" / "reference" / "main.py"
OBSERVABILITY_YAML = REPO_ROOT / "config" / "aurora" / "observability.yaml"
CONFIG_DIR = REPO_ROOT / "config"

# ---------------------------------------------------------------------------
# Test 1 — _MAIN_LOOP_CADENCE_SEC constant is exactly 1
# ---------------------------------------------------------------------------


def test_main_loop_cadence_constant_equals_1():
    """_MAIN_LOOP_CADENCE_SEC must be defined in main.py and equal to 1.

    The canonical value is 1 second.  Changing it without a timer governance
    audit degrades alert precision and loop resolution.
    """
    import importlib.util
    import sys

    # Parse the module to extract the constant without executing side-effects.
    source = MAIN_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN_PY))

    # Walk top-level assignments looking for _MAIN_LOOP_CADENCE_SEC = <int>
    constant_value = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_MAIN_LOOP_CADENCE_SEC":
                    if isinstance(node.value, ast.Constant):
                        constant_value = node.value.value
    assert constant_value is not None, (
        "main.py does not define _MAIN_LOOP_CADENCE_SEC.  "
        "Add: _MAIN_LOOP_CADENCE_SEC = 1  # infrastructure cadence floor"
    )
    assert constant_value == 1, (
        f"_MAIN_LOOP_CADENCE_SEC = {constant_value!r}, expected 1.  "
        "Do not change this value without a full timer governance audit."
    )


# ---------------------------------------------------------------------------
# Test 2 — the main loop uses the named constant, not a bare literal
# ---------------------------------------------------------------------------


def test_main_loop_uses_named_constant_not_literal():
    """The main while-True loop must call time.sleep(_MAIN_LOOP_CADENCE_SEC).

    A bare time.sleep(1) inside the runtime loop is a governance violation.
    The startup portfolio-wait loop (time.sleep(1.0)) is exempt — that is a
    separate polling pattern and uses a float literal which does not match the
    bare-int pattern checked here.
    """
    source = MAIN_PY.read_text(encoding="utf-8")
    lines = source.splitlines()

    # Locate the main while True loop (first occurrence after "Step 5")
    loop_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "while True:":
            loop_start = i
            break

    assert loop_start is not None, (
        "Could not locate 'while True:' in main.py.  "
        "The main runtime loop structure may have changed."
    )

    # Collect lines from the loop body
    loop_body = "\n".join(lines[loop_start:loop_start + 60])

    # A bare time.sleep(1) (integer, not float) in the loop body is a violation.
    # We check the AST of just the loop section for robustness.
    # Wrap with a dummy function so we can parse a partial snippet.
    snippet = "def _loop_body():\n" + textwrap.indent(
        "\n".join(lines[loop_start + 1: loop_start + 60]),
        "    ",
    )
    try:
        tree = ast.parse(snippet)
    except SyntaxError:
        # Partial snippet may not parse cleanly; fall back to text scan.
        assert "time.sleep(1)" not in loop_body, (
            "main.py runtime loop still contains bare time.sleep(1).  "
            "Replace with time.sleep(_MAIN_LOOP_CADENCE_SEC)."
        )
        return

    # Walk the AST looking for Call(func=Attribute(attr='sleep'), args=[Constant(1)])
    # where the constant is an exact integer 1 (not 1.0).
    bare_sleep_found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(getattr(node, "func", None), ast.Attribute)
            and node.func.attr == "sleep"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 1
            and isinstance(node.args[0].value, int)
        ):
            bare_sleep_found = True
            break

    assert not bare_sleep_found, (
        "main.py runtime loop contains bare time.sleep(1).  "
        "Replace with time.sleep(_MAIN_LOOP_CADENCE_SEC)."
    )

    # Positive check: named constant must appear in the loop body.
    assert "_MAIN_LOOP_CADENCE_SEC" in loop_body, (
        "main.py runtime loop does not call time.sleep(_MAIN_LOOP_CADENCE_SEC).  "
        "Ensure the named constant is used in the while-True loop."
    )


# ---------------------------------------------------------------------------
# Test 3 — main loop cadence is semantically separate from alert interval
# ---------------------------------------------------------------------------


def test_main_loop_cadence_separate_from_alert_interval():
    """_MAIN_LOOP_CADENCE_SEC (1) must differ from alerts.check_interval_sec (60).

    The 1s cadence is a granularity floor; the 60s alert interval is policy.
    Equality would indicate semantic collapse and a governance violation.
    """
    raw = yaml.safe_load(OBSERVABILITY_YAML.read_text(encoding="utf-8"))
    alert_interval = (raw.get("alerts") or {}).get("check_interval_sec")

    assert alert_interval is not None, (
        "observability.yaml is missing alerts.check_interval_sec.  "
        "Cannot verify semantic separation."
    )

    main_loop_cadence = 1  # canonical value tested in test_1

    assert main_loop_cadence != alert_interval, (
        f"_MAIN_LOOP_CADENCE_SEC ({main_loop_cadence}) == "
        f"alerts.check_interval_sec ({alert_interval}).  "
        "These must remain semantically separate: loop cadence is infrastructure "
        "granularity, alert interval is operator-configured policy."
    )


# ---------------------------------------------------------------------------
# Test 4 — no YAML key main_loop_cadence_sec was introduced
# ---------------------------------------------------------------------------


def test_no_yaml_main_loop_cadence_introduced():
    """No config YAML file must contain the key main_loop_cadence_sec.

    The loop cadence is infrastructure, not operator policy.  Introducing a
    YAML key for it would invite misconfiguration that degrades alert precision
    and handle_tick resolution without any operator benefit.
    """
    yaml_files = list(CONFIG_DIR.rglob("*.yaml"))
    violations = []
    for yf in yaml_files:
        try:
            text = yf.read_text(encoding="utf-8")
        except Exception:
            continue
        if "main_loop_cadence_sec" in text:
            violations.append(str(yf.relative_to(REPO_ROOT)))

    assert not violations, (
        "The following config files contain main_loop_cadence_sec, which must "
        "NOT exist (main loop cadence is infrastructure, not policy):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
