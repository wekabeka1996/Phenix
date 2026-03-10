from _compat import execute, reexport

_TARGET = "analysis/analyze_test_results.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
