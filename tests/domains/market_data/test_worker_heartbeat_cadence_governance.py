"""
T4B Governance: Market Data Worker Telemetry Heartbeat Cadence.

Classifies asyncio.sleep(5) in _send_heartbeat() as MARKET_DATA_TELEMETRY_HEARTBEAT:
an internal IPC diagnostic cadence, semantically distinct from ws_heartbeat_sec
(WebSocket ping/pong configured in system.yaml).

These tests lock in:
1. The constant exists and equals 5.
2. It is distinct from ws_heartbeat_sec (proves semantic separation).
3. worker.py does NOT use ws_heartbeat_sec inside _send_heartbeat (prevents conflation).
4. The constant drives the heartbeat sleep (not bypassed by a raw literal).
"""
import ast
import inspect
import pathlib
import textwrap

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
_WORKER_PATH = (
    _REPO_ROOT
    / "apps" / "reference" / "domains" / "market_data" / "worker.py"
)
_SYSTEM_YAML = _REPO_ROOT / "config" / "aurora" / "system.yaml"


# ---------------------------------------------------------------------------
# Test 1 — named constant exists and equals 5
# ---------------------------------------------------------------------------
def test_heartbeat_constant_exists_and_equals_5():
    """_MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC must be defined at module level and equal 5."""
    from apps.reference.domains.market_data.worker import (
        _MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC,
    )

    assert _MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC == 5, (
        f"Expected 5, got {_MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC}. "
        "Do not change the telemetry cadence without a governance review."
    )


# ---------------------------------------------------------------------------
# Test 2 — telemetry constant is NOT the same as ws_heartbeat_sec
# ---------------------------------------------------------------------------
def test_heartbeat_is_separate_from_ws_heartbeat_sec():
    """
    The IPC telemetry cadence (5 s) must be different from ws_heartbeat_sec (20 s).
    This proves semantic separation: one is an internal diagnostic interval,
    the other is the WebSocket ping/pong interval.
    """
    from apps.reference.domains.market_data.worker import (
        _MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC,
    )

    assert _SYSTEM_YAML.exists(), f"system.yaml not found at {_SYSTEM_YAML}"
    with _SYSTEM_YAML.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    ws_heartbeat_sec = cfg["system"]["market_data"]["ws_heartbeat_sec"]

    assert isinstance(ws_heartbeat_sec, (int, float)), (
        "system.yaml: system.market_data.ws_heartbeat_sec is not numeric"
    )
    assert _MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC != ws_heartbeat_sec, (
        f"Telemetry interval ({_MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC}) "
        f"must differ from ws_heartbeat_sec ({ws_heartbeat_sec}). "
        "These are semantically distinct: IPC diagnostic cadence vs WS ping/pong."
    )


# ---------------------------------------------------------------------------
# Test 3 — _send_heartbeat does NOT reference ws_heartbeat_sec
# ---------------------------------------------------------------------------
def test_worker_does_not_use_ws_heartbeat_sec_for_telemetry_sleep():
    """
    Inspect the AST of _send_heartbeat to confirm it never references
    ws_heartbeat_sec or _ws_heartbeat_sec.  Prevents future conflation of the
    two semantically distinct cadences.
    """
    source = _WORKER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Locate the _send_heartbeat function node
    send_hb_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_heartbeat":
            send_hb_node = node
            break

    assert send_hb_node is not None, (
        "_send_heartbeat not found in worker.py — was it renamed?"
    )

    # Collect all Name and Attribute identifiers used inside the function
    forbidden = {"ws_heartbeat_sec", "_ws_heartbeat_sec"}
    names_used: set[str] = set()
    for child in ast.walk(send_hb_node):
        if isinstance(child, ast.Name):
            names_used.add(child.id)
        elif isinstance(child, ast.Attribute):
            names_used.add(child.attr)

    conflicts = forbidden & names_used
    assert not conflicts, (
        f"_send_heartbeat references {conflicts} — "
        "this conflates WebSocket ping/pong cadence with IPC telemetry cadence. "
        "Use _MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC instead."
    )


# ---------------------------------------------------------------------------
# Test 4 — the constant is actually used in the heartbeat loop sleep call
# ---------------------------------------------------------------------------
def test_heartbeat_constant_used_in_heartbeat_loop():
    """
    Confirm that _send_heartbeat contains an asyncio.sleep call whose argument
    is the named constant, not a bare integer literal.
    """
    source = _WORKER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find _send_heartbeat
    send_hb_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_heartbeat":
            send_hb_node = node
            break

    assert send_hb_node is not None, "_send_heartbeat not found in worker.py"

    # Walk the function body looking for asyncio.sleep(<Name>)
    constant_name = "_MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC"
    found_constant_sleep = False
    found_raw_literal_sleep = False

    for node in ast.walk(send_hb_node):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        # Match asyncio.sleep(...)
        func = call.func
        is_sleep = (
            (isinstance(func, ast.Attribute) and func.attr == "sleep")
            or (isinstance(func, ast.Name) and func.id == "sleep")
        )
        if not is_sleep or not call.args:
            continue
        arg = call.args[0]
        if isinstance(arg, ast.Name) and arg.id == constant_name:
            found_constant_sleep = True
        elif isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
            found_raw_literal_sleep = True

    assert found_constant_sleep, (
        f"_send_heartbeat does not call asyncio.sleep({constant_name}). "
        "The named constant is not wired into the heartbeat loop."
    )
    assert not found_raw_literal_sleep, (
        "_send_heartbeat still contains a raw numeric sleep literal. "
        "Replace it with _MARKET_DATA_TELEMETRY_HEARTBEAT_INTERVAL_SEC."
    )
