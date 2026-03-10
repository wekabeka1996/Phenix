from _compat import execute, reexport

_TARGET = "maintenance/sanitize_repo_bytes.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
