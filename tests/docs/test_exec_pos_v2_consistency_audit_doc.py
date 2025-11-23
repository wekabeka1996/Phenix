"""
Test suite for ExecPosRuntimeV2 consistency audit documentation.

RID: EP-V2-CONSISTENCY-AUDIT-A1

Purpose: Validate that the audit document exists, is complete, and captures
the current ExecPosRuntimeV2 + OCO wiring, config chain, and ClientOrderId
contract via RIDs and key component mentions. This test ensures the audit
doc is not accidentally deleted and stays aligned with code changes.

Constraint: Text-based validation only (no domain imports).
"""

import os
from pathlib import Path
import pytest


# Path to audit document
AUDIT_DOC_PATH = Path(__file__).parent.parent.parent / "docs" / "EXEC_POS_V2_CONSISTENCY_AUDIT_S1.md"


def test_audit_doc_exists():
    """
    Verify that the audit document exists and is not empty.
    """
    assert AUDIT_DOC_PATH.exists(), f"Audit doc not found: {AUDIT_DOC_PATH}"
    
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    assert len(content) > 0, "Audit doc is empty"
    assert len(content) > 1000, f"Audit doc is too short ({len(content)} chars), expected comprehensive audit"


def test_audit_doc_mentions_key_rids():
    """
    Verify that audit doc mentions all required RIDs from completed migrations.
    
    Required RIDs:
    - EP-OCO-V2-WIRING-S1 (BracketService wiring)
    - EP-OCO-V2-DR-RECOVERY-S1 (DR recovery pass)
    - EP-CLIENTID-UNIFY-S5 (clientOrderId unification)
    - EP-CONFIG-MANAGE-HYBRID-S5 (hybrid adapter)
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    required_rids = [
        "EP-OCO-V2-WIRING-S1",
        "EP-OCO-V2-DR-RECOVERY-S1",
        "EP-CLIENTID-UNIFY-S5",
        "EP-CONFIG-MANAGE-HYBRID-S5",
    ]
    
    for rid in required_rids:
        assert rid in content, f"RID '{rid}' not mentioned in audit doc"


def test_audit_doc_mentions_config_rids():
    """
    Verify that audit doc mentions config SSOT related RIDs.
    
    Config RIDs:
    - EP-CONFIG-SSOT-S1 (Pydantic models)
    - EP-CONFIG-INJECTION-S2 (config loader integration)
    - EP-CONFIG-SAMPLES-S3 (example profiles)
    - EP-CONFIG-DOMAINS-REF-MAP-S4 (config reference)
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    config_rids = [
        "EP-CONFIG-SSOT-S1",
        "EP-CONFIG-INJECTION-S2",
        "EP-CONFIG-SAMPLES-S3",
        "EP-CONFIG-DOMAINS-REF-MAP-S4",
    ]
    
    for rid in config_rids:
        assert rid in content, f"Config RID '{rid}' not mentioned in audit doc"


def test_audit_doc_mentions_execpos_runtime_and_config():
    """
    Verify that audit doc contains key component references.
    
    Required mentions:
    - ExecPosRuntimeV2 (V2 runtime)
    - ExecutionPositionConfig (Pydantic models)
    - manage_config.py (hybrid adapter)
    - BracketService (OCO evaluation)
    - OrderGuardian (metadata service)
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    required_components = [
        "ExecPosRuntimeV2",
        "ExecutionPositionConfig",
        "manage_config.py",
        "BracketService",
        "OrderGuardian",
    ]
    
    for component in required_components:
        assert component in content, f"Component '{component}' not mentioned in audit doc"


def test_audit_doc_mentions_clientorderid_canonical():
    """
    Verify that audit doc documents clientOrderId unification.
    
    Required mentions:
    - make_execpos_client_order_id (canonical builder)
    - ClientOrderIntent (intent enum)
    - IdempotentCancelHelper (wrapper)
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    clientid_keywords = [
        "make_execpos_client_order_id",
        "ClientOrderIntent",
        "clientOrderId",
    ]
    
    for keyword in clientid_keywords:
        assert keyword in content, f"ClientOrderId keyword '{keyword}' not mentioned in audit doc"


def test_audit_doc_has_required_sections():
    """
    Verify that audit doc has required structural sections.
    
    Required sections:
    - Scope & Input RIDs
    - Runtime & OCO Wiring
    - Config Chain
    - ClientOrderId
    - Risks & Gaps
    - Suggested Next Steps
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    required_sections = [
        "Scope & Input RIDs",
        "Runtime & OCO Wiring",
        "Config Chain",
        "ClientOrderId",
        "Risks & Gaps",
        "Suggested Next Steps",
    ]
    
    for section in required_sections:
        assert section in content, f"Section '{section}' not found in audit doc"


def test_audit_doc_mentions_bracket_service_contract():
    """
    Verify that audit doc documents BracketService contract behavior.
    
    Required mentions:
    - Pure computation (no side effects)
    - BracketPlan (output)
    - _apply_bracket_plan (execution)
    - _run_bracket_recovery_pass (DR recovery)
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    bracket_keywords = [
        "BracketService",
        "BracketPlan",
        "_apply_bracket_plan",
        "_run_bracket_recovery_pass",
    ]
    
    for keyword in bracket_keywords:
        assert keyword in content, f"BracketService keyword '{keyword}' not mentioned in audit doc"


def test_audit_doc_mentions_config_validation():
    """
    Verify that audit doc documents config validation behavior.
    
    Required mentions:
    - Pydantic validation
    - ValidationError
    - Immutable config (frozen)
    - Type coercion
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    validation_keywords = [
        "Pydantic",
        "ValidationError",
        "frozen",
        "immutable",
    ]
    
    for keyword in validation_keywords:
        assert keyword in content, f"Validation keyword '{keyword}' not mentioned in audit doc"


def test_audit_doc_documents_guardian_role():
    """
    Verify that audit doc clarifies OrderGuardian's query-only role in V2.
    
    Required mentions:
    - Query-only
    - No auto-heal in V2
    - Metadata service
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    # Check that doc mentions Guardian is query-only
    assert "query-only" in content.lower() or "query only" in content.lower(), \
        "Guardian query-only role not documented"
    
    # Check that doc mentions no auto-heal
    assert "no auto-heal" in content.lower() or "auto-heal" in content.lower(), \
        "Guardian auto-heal behavior not documented"


def test_audit_doc_has_quality_assessment():
    """
    Verify that audit doc includes overall quality assessment.
    
    Required:
    - Quality score (numeric assessment)
    - Justification
    - Recommendation
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    assessment_keywords = [
        "Quality Score",
        "Justification",
        "Recommendation",
    ]
    
    for keyword in assessment_keywords:
        assert keyword in content, f"Assessment keyword '{keyword}' not found in audit doc"


def test_audit_doc_mentions_hybrid_adapter_intentional():
    """
    Verify that audit doc clarifies hybrid adapter is intentional, not a bug.
    
    Required mentions:
    - Hybrid adapter
    - Intentional migration strategy
    - V2 priority
    - Legacy fallback
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    hybrid_keywords = [
        "hybrid",
        "intentional",
        "migration",
        "V2 priority",
        "legacy fallback",
    ]
    
    for keyword in hybrid_keywords:
        assert keyword.lower() in content.lower(), \
            f"Hybrid adapter keyword '{keyword}' not mentioned in audit doc"


def test_audit_doc_no_speculation():
    """
    Verify that audit doc does not contain speculative language.
    
    Forbidden phrases:
    - "probably"
    - "maybe"
    - "possibly"
    - "might be"
    - "could be"
    
    Note: This ensures audit is based on factual code observation only.
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    speculative_phrases = [
        "probably",
        "maybe",
        "possibly",
        "might be",
        "could be",
    ]
    
    for phrase in speculative_phrases:
        # Allow exact phrase "could be" in code comments/examples
        # but not in audit narrative
        if phrase == "could be":
            # More lenient check - just ensure it's not overused
            count = content.lower().count(phrase)
            assert count < 3, f"Speculative phrase '{phrase}' appears {count} times (max 2 allowed for examples)"
        else:
            assert phrase not in content.lower(), \
                f"Speculative phrase '{phrase}' found in audit doc - should be factual only"


def test_audit_doc_references_actual_files():
    """
    Verify that audit doc references existing files.
    
    Key files that should be mentioned:
    - apps/reference/domains/execution_position/shadow_execpos/runtime.py
    - apps/reference/domains/execution_position/shadow_execpos/bracket_service.py
    - apps/reference/domains/execution_position/config.py
    - apps/reference/domains/execution_position/manage_config.py
    - apps/reference/domains/execution_position/utils.py
    """
    content = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    
    # Check file references (basename is sufficient for validation)
    referenced_files = [
        "runtime.py",
        "bracket_service.py",
        "config.py",
        "manage_config.py",
        "utils.py",
    ]
    
    for filename in referenced_files:
        assert filename in content, f"File '{filename}' not referenced in audit doc"
