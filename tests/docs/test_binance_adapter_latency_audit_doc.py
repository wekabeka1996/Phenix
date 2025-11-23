"""Test for BINANCE_ADAPTER_LATENCY_AUDIT_S1.md existence and completeness.

This test ensures the latency audit document exists and contains references
to key concepts related to async time sync migration (S12).
"""

import re
from pathlib import Path


def test_latency_audit_doc_exists():
    """Verify that the latency audit document exists."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    assert doc_path.exists(), f"Latency audit doc not found at {doc_path}"


def test_latency_audit_doc_not_empty():
    """Verify that the latency audit document has content."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Document should be substantial (at least 100 lines)
    lines = content.split('\n')
    assert len(
        lines) >= 100, f"Document too short: {len(lines)} lines (expected 100+)"


def test_latency_audit_mentions_rid():
    """Verify that the document mentions the RID for S12."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention the RID
    assert "EP-ADAPTER-BINANCE-ASYNC-TIME-SYNC-S12" in content, \
        "Document does not mention RID: EP-ADAPTER-BINANCE-ASYNC-TIME-SYNC-S12"


def test_latency_audit_mentions_sync_time_function():
    """Verify that the document mentions _sync_time_with_server."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention the function being migrated
    assert "_sync_time_with_server" in content, \
        "Document does not mention _sync_time_with_server function"


def test_latency_audit_mentions_httpx():
    """Verify that the document mentions httpx.AsyncClient."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention httpx as the async HTTP client
    assert "httpx" in content.lower(), \
        "Document does not mention httpx"

    # Should specifically mention AsyncClient
    assert "AsyncClient" in content, \
        "Document does not mention httpx.AsyncClient"


def test_latency_audit_mentions_execution_position():
    """Verify that the document discusses execution_position domain."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention execution_position domain
    assert "execution_position" in content, \
        "Document does not mention execution_position domain"


def test_latency_audit_has_required_sections():
    """Verify that the document has all required sections."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    required_sections = [
        "## Overview",
        "## Current State",
        "## Changes in EP-ADAPTER-BINANCE-ASYNC-TIME-SYNC-S12",
        "## Latency & Safety Considerations",
    ]

    for section in required_sections:
        assert section in content, f"Document missing required section: {section}"


def test_latency_audit_discusses_blocking_io():
    """Verify that the document discusses blocking I/O problem."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should discuss blocking as the core problem
    blocking_terms = ["blocking", "event loop", "async", "await"]
    found_terms = [term for term in blocking_terms if term.lower()
                   in content.lower()]

    assert len(found_terms) >= 3, \
        f"Document does not sufficiently discuss blocking I/O issue (found terms: {found_terms})"


def test_latency_audit_mentions_callsites():
    """Verify that the document discusses call sites."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention some key async methods that call time sync
    key_methods = [
        "get_open_positions",
        "get_open_orders",
        "place_order"  # or _place_binance_order_async
    ]

    found_methods = [method for method in key_methods if method in content]
    assert len(found_methods) >= 2, \
        f"Document does not mention enough call sites (found: {found_methods})"


def test_latency_audit_discusses_execpos_v2():
    """Verify that the document discusses connection to ExecPos V2."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should discuss V2 runtime or shadow_execpos
    v2_terms = ["V2", "shadow_execpos", "runtime"]
    found_terms = [term for term in v2_terms if term in content]

    assert len(found_terms) >= 2, \
        f"Document does not discuss ExecPos V2 connection (found terms: {found_terms})"


def test_latency_audit_has_latency_metrics():
    """Verify that the document mentions latency metrics or targets."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "BINANCE_ADAPTER_LATENCY_AUDIT_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention latency measurements or targets
    latency_indicators = ["ms", "latency", "p95", "p99"]
    found_indicators = [ind for ind in latency_indicators if ind in content]

    assert len(found_indicators) >= 2, \
        f"Document does not discuss latency metrics (found: {found_indicators})"
