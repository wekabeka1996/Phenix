from _compat import execute, reexport

_TARGET = "forensics/deep_wal_forensics.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
