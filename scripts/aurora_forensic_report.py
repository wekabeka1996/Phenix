from _compat import execute, reexport

_TARGET = "forensics/aurora_forensic_report.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
