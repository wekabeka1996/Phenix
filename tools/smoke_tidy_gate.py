from _compat import execute, reexport

_TARGET = "diagnostics/smoke_tidy_gate.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
