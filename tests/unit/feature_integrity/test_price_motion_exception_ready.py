"""
Contract test: compute_price_motion_block exception handler correctness.

PRICE-MOTION-EXCEPTION-CONTRACT-01:
When compute_price_motion_block raises, the except handler MUST:
  - Set warmup["ready"]["price_motion"] = False
  - Set warmup["full_ready"] = False
  - Append a reason containing "price_motion" to warmup["reasons"]

Tests are AST-based to avoid full FeatureEngineering integration setup.
The code contract is verified at source level — no silent degradation allowed.
"""
import ast
import pathlib
import pytest


ROOT = pathlib.Path(
    "apps/reference/domains/feature_engineering/feature_engineering.py")


def _has_direct_call(stmts: list, func_name: str) -> bool:
    """
    Return True if any of the given statements is a direct call (or assignment
    from a call) to `func_name` — without recursing into nested try/for/with blocks.
    """
    for stmt in stmts:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            f = stmt.value.func
            if isinstance(f, ast.Name) and f.id == func_name:
                return True
            if isinstance(f, ast.Attribute) and f.attr == func_name:
                return True
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            f = stmt.value.func
            if isinstance(f, ast.Name) and f.id == func_name:
                return True
    return False


def _find_pm_except_handler_src() -> str:
    """
    Find the except handler of the try block whose DIRECT body calls
    compute_price_motion_block (not a parent/outer try block).
    Returns the unparsed handler body as a string, or empty string if not found.
    """
    source = ROOT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not _has_direct_call(node.body, "compute_price_motion_block"):
            continue
        if not node.handlers:
            continue
        return "\n".join(ast.unparse(stmt) for stmt in node.handlers[0].body)

    return ""


class TestPriceMotionExceptionContract:
    """
    Verify every required side-effect of the except block that wraps
    compute_price_motion_block is actually present in the source code.
    """

    def test_price_motion_block_is_wrapped_in_try(self):
        """compute_price_motion_block must be inside a try block."""
        source = ROOT.read_text(encoding="utf-8")
        tree = ast.parse(source)

        found = any(
            _has_direct_call(node.body, "compute_price_motion_block")
            for node in ast.walk(tree)
            if isinstance(node, ast.Try)
        )
        assert found, (
            "compute_price_motion_block must be wrapped in try/except. "
            "An unhandled exception here would crash the tick loop."
        )

    def test_except_block_sets_price_motion_false(self):
        """
        Contract: ready_map["price_motion"] = False must appear in the except block.
        Without this, a failed computation silently passes None values to scoring.
        """
        handler_src = _find_pm_except_handler_src()
        assert handler_src, "compute_price_motion_block try/except handler not found"

        assert "price_motion" in handler_src, (
            "except block does not reference 'price_motion'. "
            "Failed price_motion computation must explicitly mark itself as not-ready."
        )
        assert "False" in handler_src, (
            "except block does not assign False anywhere. "
            "ready_map[\"price_motion\"] = False is required."
        )

    def test_except_block_sets_full_ready_false(self):
        """
        Contract: warmup["full_ready"] = False must appear in the except block.
        A partial feature failure should prevent the system from going fully ready.
        """
        handler_src = _find_pm_except_handler_src()
        assert handler_src, "compute_price_motion_block try/except handler not found"

        assert "full_ready" in handler_src, (
            "except block does not set full_ready = False. "
            "price_motion failure must propagate to warmup.full_ready."
        )

    def test_except_block_appends_to_reasons(self):
        """
        Contract: warmup["reasons"] must be updated in the except block.
        Operators need a diagnostic trail to understand why scoring deferred.
        """
        handler_src = _find_pm_except_handler_src()
        assert handler_src, "compute_price_motion_block try/except handler not found"

        assert "reasons" in handler_src, (
            "except block does not append to warmup['reasons']. "
            "Fail-loud requires a diagnostic reason string."
        )

    def test_except_block_is_not_silent_pass(self):
        """
        Anti-pattern guard: the except block must not be just a `pass` or comment.
        A silent swallow here would leave scoring with None values and no signal.
        """
        source = ROOT.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            body_src = "\n".join(ast.unparse(s) for s in node.body)
            if "compute_price_motion_block" not in body_src:
                continue
            for handler in node.handlers:
                for stmt in handler.body:
                    if not isinstance(stmt, ast.Pass):
                        return  # handler has real statements
                pytest.fail(
                    "compute_price_motion_block except block is empty (only `pass`). "
                    "This is a silent swallow — fail-loud contract violated."
                )
