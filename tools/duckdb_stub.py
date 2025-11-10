"""
Minimal in-project stub of duckdb API used by FeatureStore for test execution
without the native dependency.

Implements `connect(path)` returning a context manager with `execute()` that
no-ops and returns self.
"""

class _Conn:
    def __init__(self, path: str):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    # DuckDB API compatibility (very minimal)
    def execute(self, *_args, **_kwargs):
        return self


def connect(path: str):
    return _Conn(path)

