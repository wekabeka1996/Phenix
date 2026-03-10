from _compat import execute, reexport

_TARGET = "forensics/wal_intent_summary.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
