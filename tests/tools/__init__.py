"""Tools tests package.

Pytest can import this directory as top-level ``tools`` during full-suite collection
when the tests directory is placed ahead of the repository root on ``sys.path``.
Extend the package search path so ``tools.*`` continues resolving to the real
workspace package instead of failing under the test package shadow.
"""

from pathlib import Path


_REAL_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if _REAL_TOOLS_DIR.is_dir():
    __path__.append(str(_REAL_TOOLS_DIR))
