from _compat import execute, reexport

_TARGET = "backtest/backtest_summarize.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
