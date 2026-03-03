"""
Contract test: broad `except Exception` narrowing in types.py (Tier 1.2).

T1-2-EXCEPTION-NARROWING-CONTRACT:
After the Tier 1.2 fix, these three locations in types.py must NOT use bare
`except Exception` (which swallows any unexpected runtime error silently):

  1. large_trade_imbalance_enabled  (property)  → must use except AttributeError
  2. macro_sync_max_late_ms         (property)  → must use except AttributeError
  3. compute_warmup_full_ready_for_symbol       → must use except (AttributeError, TypeError, KeyError)

Broad `except Exception` is dangerous because it silently swallows
TypeError, RuntimeError, NameError, etc. that indicate real bugs.

Tests are AST-based — if someone reverts the fix, the test suite catches it
before production.
"""
import ast
import pathlib
import pytest


ROOT = pathlib.Path("apps/reference/domains/feature_engineering/types.py")


def _get_source() -> str:
    return ROOT.read_text(encoding="utf-8")


def _find_except_exception_lines(source: str, function_name: str) -> list[int]:
    """
    Return line numbers of bare `except Exception` or `except:` blocks
    inside the named function or property.
    """
    tree = ast.parse(source)
    bad_lines: list[int] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.ExceptHandler):
                continue
            if child.type is None:
                # bare `except:`
                bad_lines.append(child.lineno)
            elif isinstance(child.type, ast.Name) and child.type.id == "Exception":
                # `except Exception` or `except Exception as e`
                bad_lines.append(child.lineno)

    return bad_lines


class TestExceptionNarrowing:
    """All three Tier 1.2 fixes must be in place."""

    def test_large_trade_imbalance_enabled_no_broad_except(self):
        """
        large_trade_imbalance_enabled must not catch bare Exception.
        The original bug: except Exception silently returned True even for
        unexpected errors (e.g., ImportError, RuntimeError).
        Fix: except AttributeError (the only expected error here).
        """
        source = _get_source()
        bad = _find_except_exception_lines(
            source, "large_trade_imbalance_enabled")
        assert not bad, (
            f"large_trade_imbalance_enabled still has broad 'except Exception' "
            f"at line(s): {bad}. Must use 'except AttributeError'."
        )

    def test_macro_sync_max_late_ms_no_broad_except(self):
        """
        macro_sync_max_late_ms must not catch bare Exception.
        The original bug: except Exception silently returned 0, masking
        any unexpected error in the macro_sync config access path.
        Fix: except AttributeError.
        """
        source = _get_source()
        bad = _find_except_exception_lines(source, "macro_sync_max_late_ms")
        assert not bad, (
            f"macro_sync_max_late_ms still has broad 'except Exception' "
            f"at line(s): {bad}. Must use 'except AttributeError'."
        )

    def test_compute_warmup_no_broad_except(self):
        """
        compute_warmup_full_ready_for_symbol must not catch bare Exception.
        The original bug: a TypeError in the list comprehension (line with
        `[str(k) for k in by_symbol[symbol]]`) would silently set
        override_keys = None, causing warmup to use default required keys
        without any error signal.
        Fix: except (AttributeError, TypeError, KeyError).
        """
        source = _get_source()
        bad = _find_except_exception_lines(
            source, "compute_warmup_full_ready_for_symbol")
        assert not bad, (
            f"compute_warmup_full_ready_for_symbol still has broad 'except Exception' "
            f"at line(s): {bad}. Must use 'except (AttributeError, TypeError, KeyError)'."
        )

    def test_compute_warmup_uses_specific_tuple_exceptions(self):
        """
        compute_warmup_full_ready_for_symbol must catch exactly the expected
        tuple of exceptions — not a single broad type.
        """
        source = _get_source()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "compute_warmup_full_ready_for_symbol":
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.ExceptHandler):
                    continue
                assert isinstance(child.type, ast.Tuple), (
                    "compute_warmup_full_ready_for_symbol except handler must catch "
                    "a tuple of exception types, not a single broad type."
                )
                caught = [
                    elt.id for elt in child.type.elts if isinstance(elt, ast.Name)
                ]
                assert "AttributeError" in caught, (
                    f"AttributeError missing from except tuple: {caught}"
                )
                assert "TypeError" in caught, (
                    f"TypeError missing from except tuple: {caught}"
                )
                assert "Exception" not in caught, (
                    f"'Exception' must not be in the tuple — too broad: {caught}"
                )
                return  # passed

        pytest.fail(
            "compute_warmup_full_ready_for_symbol has no except handler. "
            "Expected a tuple except (AttributeError, TypeError, KeyError)."
        )
