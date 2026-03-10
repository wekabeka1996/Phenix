from _compat import execute, reexport

_TARGET = "testing/run_tests.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
