from _compat import execute, reexport

_TARGET = "monitoring/live_observability_summary.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
