# -*- coding: utf-8 -*-
"""
Tests for EXEC_POSITION_CONFIG_FIELD_USAGE_REPORT_S1.md completeness and accuracy.

RID: EP-CONFIG-FIELD-USAGE-REPORT-S6

Purpose:
- Validate report file exists and is not empty
- Ensure all ExecutionPositionConfig fields are mentioned in report
- Verify UNUSED/DOC_ONLY fields are explicitly marked

Related: docs/EXEC_POSITION_CONFIG_FIELD_USAGE_REPORT_S1.md
"""

from apps.reference.domains.execution_position.config import (
    AggregatedOcoConfig,
    AggregatedOcoWatchdogConfig,
    AggregatedOcoWatchdogGraceConfig,
    CloseConfig,
    ExecutionPositionConfig,
    TrailingConfig,
)
import sys
from pathlib import Path
from typing import Set

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Path to report file
REPORT_PATH = PROJECT_ROOT / "docs" / \
    "EXEC_POSITION_CONFIG_FIELD_USAGE_REPORT_S1.md"


def _get_all_config_fields() -> Set[str]:
    """
    Extract all field names from ExecutionPositionConfig using reflection.

    Returns:
        Set of field_path strings (e.g., "aggregated_oco.sl_pct", "trailing.enabled").
    """
    fields = set()

    # Root fields
    for field_name in ExecutionPositionConfig.model_fields:
        fields.add(field_name)

    # AggregatedOcoConfig fields
    for field_name in AggregatedOcoConfig.model_fields:
        fields.add(f"aggregated_oco.{field_name}")

    # AggregatedOcoWatchdogConfig fields
    for field_name in AggregatedOcoWatchdogConfig.model_fields:
        fields.add(f"aggregated_oco.watchdog.{field_name}")

    # AggregatedOcoWatchdogGraceConfig fields
    for field_name in AggregatedOcoWatchdogGraceConfig.model_fields:
        fields.add(f"aggregated_oco.watchdog.grace.{field_name}")

    # TrailingConfig fields
    for field_name in TrailingConfig.model_fields:
        fields.add(f"trailing.{field_name}")

    # CloseConfig fields
    for field_name in CloseConfig.model_fields:
        fields.add(f"close.{field_name}")

    return fields


def test_report_file_exists_and_not_empty():
    """
    Test 1: Report file exists and has non-zero size.

    Ensures EXEC_POSITION_CONFIG_FIELD_USAGE_REPORT_S1.md was created and populated.
    """
    assert REPORT_PATH.exists(), f"Report file missing: {REPORT_PATH}"
    assert REPORT_PATH.stat(
    ).st_size > 0, f"Report file is empty: {REPORT_PATH}"

    # Sanity check: report should have at least 100 lines (comprehensive doc)
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    line_count = len(report_text.splitlines())
    assert line_count >= 100, f"Report too short ({line_count} lines), expected >= 100"


def test_all_config_fields_mentioned_in_report():
    """
    Test 2: All ExecutionPositionConfig fields are mentioned in report.

    Uses reflection to collect all field_path strings (e.g., "aggregated_oco.sl_pct"),
    then checks that each field appears in the report text.

    Failure indicates a field was added to config.py but not documented in usage report.
    """
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    all_fields = _get_all_config_fields()

    missing_fields = []
    for field_path in all_fields:
        # Check if field_path appears in report (anywhere in text)
        if field_path not in report_text:
            missing_fields.append(field_path)

    assert not missing_fields, (
        f"{len(missing_fields)} fields missing from report:\n"
        + "\n".join(f"  - {field}" for field in sorted(missing_fields))
        + f"\n\nReport path: {REPORT_PATH}"
    )


def test_unused_fields_are_explicitly_marked():
    """
    Test 3: UNUSED or DOC_ONLY fields are explicitly marked in report.

    Checks that strings "UNUSED" or "DOC_ONLY" appear at least once in report text,
    ensuring we document fields that are declared but not consumed by runtime.

    This prevents silent accumulation of dead config fields.
    """
    report_text = REPORT_PATH.read_text(encoding="utf-8")

    # Check for explicit UNUSED/DOC_ONLY markers
    has_unused_marker = "UNUSED" in report_text
    has_doc_only_marker = "DOC_ONLY" in report_text

    assert has_unused_marker or has_doc_only_marker, (
        "Report does not explicitly mark any fields as UNUSED or DOC_ONLY. "
        f"This is suspicious (all fields used?). Report: {REPORT_PATH}"
    )

    # Sanity check: expect at least 3 UNUSED/DOC_ONLY mentions (per summary)
    unused_count = report_text.count("UNUSED")
    doc_only_count = report_text.count("DOC_ONLY")
    total_markers = unused_count + doc_only_count

    assert total_markers >= 3, (
        f"Too few UNUSED/DOC_ONLY markers ({total_markers}), expected >= 3. "
        f"Report may be incomplete. Report: {REPORT_PATH}"
    )


def test_report_has_required_sections():
    """
    Test 4 (bonus): Report has required structural sections.

    Validates report structure includes:
    - Overview
    - Model Snapshot
    - Runtime Usage Map
    - Summary

    This ensures report follows prescribed format from task spec.
    """
    report_text = REPORT_PATH.read_text(encoding="utf-8")

    required_sections = [
        "## 1. Overview",
        "## 2. Model Snapshot",
        "## 3. Runtime Usage Map",
        "## 4. Summary",
    ]

    missing_sections = []
    for section_header in required_sections:
        if section_header not in report_text:
            missing_sections.append(section_header)

    assert not missing_sections, (
        f"{len(missing_sections)} required sections missing from report:\n"
        + "\n".join(f"  - {section}" for section in missing_sections)
        + f"\n\nReport path: {REPORT_PATH}"
    )


def test_report_documents_usage_kinds():
    """
    Test 5 (bonus): Report documents usage_kind categories.

    Checks that report includes usage category definitions:
    - AGG_OCO_RULE
    - RUNTIME_PARAM
    - TRAILING_PARAM
    - DOC_ONLY
    - UNUSED

    This ensures report provides actionable categorization of field usage.
    """
    report_text = REPORT_PATH.read_text(encoding="utf-8")

    expected_categories = [
        "AGG_OCO_RULE",
        "RUNTIME_PARAM",
        "TRAILING_PARAM",
        "DOC_ONLY",
        "UNUSED",
    ]

    missing_categories = []
    for category in expected_categories:
        if category not in report_text:
            missing_categories.append(category)

    assert not missing_categories, (
        f"{len(missing_categories)} usage_kind categories missing from report:\n"
        + "\n".join(f"  - {cat}" for cat in missing_categories)
        + f"\n\nReport path: {REPORT_PATH}"
    )


def test_close_config_marked_as_unused():
    """
    Test 6 (bonus): CloseConfig fields explicitly marked as UNUSED.

    Per report scope, entire CloseConfig block (4 fields) is placeholder/unused.
    Validates that report explicitly documents this fact.
    """
    report_text = REPORT_PATH.read_text(encoding="utf-8")

    close_fields = [
        "close.max_hold_time_sec",
        "close.reason_policy",
        "close.allow_time_exit",
        "close.allow_profit_exit",
    ]

    # Check that each close field is mentioned AND marked as UNUSED
    for field_path in close_fields:
        assert field_path in report_text, f"{field_path} missing from report"

        # Find line mentioning this field and check for UNUSED marker nearby
        lines = report_text.splitlines()
        field_line_idx = None
        for idx, line in enumerate(lines):
            if field_path in line:
                field_line_idx = idx
                break

        assert field_line_idx is not None, f"{field_path} not found in report lines"

        # Check 5 lines around field mention for UNUSED/DOC_ONLY marker
        context_start = max(0, field_line_idx - 2)
        context_end = min(len(lines), field_line_idx + 3)
        context = "\n".join(lines[context_start:context_end])

        assert "UNUSED" in context or "DOC_ONLY" in context, (
            f"{field_path} not marked as UNUSED/DOC_ONLY in context:\n{context}"
        )


def test_report_summary_has_statistics():
    """
    Test 7 (bonus): Summary section includes usage statistics.

    Validates that report provides quantitative breakdown:
    - Total fields count
    - Used vs. unused counts
    - Percentage of actively used fields

    This ensures report provides actionable metrics for future cleanup.
    """
    report_text = REPORT_PATH.read_text(encoding="utf-8")

    # Check for summary section
    assert "## 4. Summary" in report_text, "Summary section missing"

    summary_section = report_text.split("## 4. Summary")[1].split("## 5.")[0]

    # Check for statistical keywords
    required_keywords = [
        "Total Fields",
        "UNUSED",
        "DOC_ONLY",
        "actively used",
    ]

    missing_keywords = []
    for keyword in required_keywords:
        if keyword not in summary_section:
            missing_keywords.append(keyword)

    assert not missing_keywords, (
        f"{len(missing_keywords)} statistical keywords missing from Summary:\n"
        + "\n".join(f"  - {kw}" for kw in missing_keywords)
        + "\n\nSummary section should include usage statistics."
    )

    # Check for numerical statistics (e.g., "16/30", "53%")
    import re

    has_fraction = bool(re.search(r"\d+/\d+", summary_section))
    has_percentage = bool(re.search(r"\d+%", summary_section))

    assert has_fraction and has_percentage, (
        "Summary section should include numerical statistics (e.g., '16/30', '53%')"
    )
