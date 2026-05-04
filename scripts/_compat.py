import runpy
import sys
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BASE_DIR.parent
_SKIP_KEYS = {
    "__name__",
    "__file__",
    "__package__",
    "__cached__",
    "__doc__",
    "__loader__",
    "__spec__",
    "__builtins__",
}


def execute(relative_path: str) -> None:
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    runpy.run_path(str(_BASE_DIR / relative_path), run_name="__main__")


def reexport(relative_path: str, namespace: dict) -> None:
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    exported = runpy.run_path(str(_BASE_DIR / relative_path))
    for key, value in exported.items():
        if key not in _SKIP_KEYS:
            namespace[key] = value
