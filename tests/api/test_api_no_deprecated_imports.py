"""
Test to ensure deprecated metrics.py is not imported by main.py.
"""

import pytest


def test_main_does_not_import_deprecated_metrics():
    """Ensure main.py does not import from deprecated api.metrics."""
    import ast
    import inspect

    from apps.reference.api import main

    # Get source of main.py
    source = inspect.getsource(main)

    # Parse AST
    tree = ast.parse(source)

    # Find all ImportFrom nodes
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(f"from {node.module} import ...")

    # Check no import from apps.reference.api.metrics
    deprecated_imports = [imp for imp in imports if "apps.reference.api.metrics" in imp]
    assert len(deprecated_imports) == 0, f"Found deprecated imports: {deprecated_imports}"