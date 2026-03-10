from _compat import execute, reexport

_TARGET = "monitoring/extract_equity_free_usdt.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
