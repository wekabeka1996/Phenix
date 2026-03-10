from _compat import execute, reexport

_TARGET = "diagnostics/feature_integrity_replay_check.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
