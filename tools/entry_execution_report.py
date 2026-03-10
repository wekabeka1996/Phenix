from _compat import execute, reexport

_TARGET = "forensics/entry_execution_report.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
