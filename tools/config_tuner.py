from _compat import execute, reexport

_TARGET = "simulation/config_tuner.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
