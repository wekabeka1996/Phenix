from _compat import execute, reexport

_TARGET = "maintenance/ascii_sanitize_repo.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
