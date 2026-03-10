import inspect
from pathlib import Path
import runpy


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


def _caller_base_dir() -> Path:
    frame = inspect.currentframe()
    if frame is None or frame.f_back is None or frame.f_back.f_back is None:
        raise RuntimeError(
            "Unable to resolve caller frame for compatibility wrapper")
    caller_globals = frame.f_back.f_back.f_globals
    caller_file = caller_globals.get("__file__")
    if not caller_file:
        raise RuntimeError("Compatibility wrapper caller has no __file__")
    return Path(caller_file).resolve().parent


def execute(relative_path: str) -> None:
    runpy.run_path(str(_caller_base_dir() / relative_path),
                   run_name="__main__")


def reexport(relative_path: str, namespace: dict) -> None:
    exported = runpy.run_path(str(_caller_base_dir() / relative_path))
    for key, value in exported.items():
        if key not in _SKIP_KEYS:
            namespace[key] = value
