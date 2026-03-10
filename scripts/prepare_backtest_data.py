from _compat import execute, reexport

_TARGET = "data/prepare_backtest_data.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
