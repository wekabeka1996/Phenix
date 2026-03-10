from _compat import execute, reexport

_TARGET = "forensics/entry_fill_audit.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
