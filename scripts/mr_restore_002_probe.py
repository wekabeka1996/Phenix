from _compat import execute, reexport

_TARGET = "diagnostics/mr_restore_002_probe.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
