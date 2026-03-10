from _compat import execute, reexport

_TARGET = "forensics/analyze_live_wal_trades.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
