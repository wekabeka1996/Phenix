from _compat import execute, reexport

_TARGET = "maintenance/remove_failed_tests.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
