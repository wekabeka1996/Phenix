from _compat import execute, reexport

_TARGET = "diagnostics/execution_vs_upstream_trace_01.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
