from _compat import execute, reexport

_TARGET = "simulation/strategy_replay.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
