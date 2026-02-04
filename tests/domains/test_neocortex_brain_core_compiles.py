import py_compile
from pathlib import Path


def test_neocortex_brain_core_py_compiles():
    core_py = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "reference"
        / "domains"
        / "neocortex"
        / "logic"
        / "brain"
        / "core.py"
    )
    assert core_py.exists(), f"Expected file to exist: {core_py}"
    py_compile.compile(str(core_py), doraise=True)
