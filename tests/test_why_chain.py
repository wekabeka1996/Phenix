"""Tests for why chain functionality"""

from vfoundation.obs.why import append_why


def test_append_why_empty_chain():
    """Test appending to empty chain"""
    chain = []
    result = append_why(chain, "first reason")
    assert result == ["first reason"]
    assert chain == []  # Original unchanged


def test_append_why_existing_chain():
    """Test appending to existing chain"""
    chain = ["reason1", "reason2"]
    result = append_why(chain, "reason3")
    assert result == ["reason1", "reason2", "reason3"]


def test_append_why_empty_string():
    """Test appending empty string (should not add)"""
    chain = ["reason1"]
    result = append_why(chain, "")
    assert result == ["reason1"]


def test_append_why_none():
    """Test appending None"""
    chain = ["reason1"]
    result = append_why(chain, None)
    assert result == ["reason1"]


def test_append_why_whitespace():
    """Test appending whitespace (should add if truthy)"""
    chain = []
    result = append_why(chain, "   ")
    assert result == ["   "]


def test_append_why_multiple_appends():
    """Test chaining multiple appends"""
    chain = []
    chain = append_why(chain, "step1")
    chain = append_why(chain, "step2")
    chain = append_why(chain, "step3")
    assert chain == ["step1", "step2", "step3"]
