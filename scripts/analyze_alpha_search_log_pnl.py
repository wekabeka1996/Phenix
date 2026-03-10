from _compat import execute, reexport

_TARGET = "analysis/analyze_alpha_search_log_pnl.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
