from _compat import execute, reexport

_TARGET = "forensics/gate_effect_report.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
