from _compat import execute, reexport

_TARGET = "testing/test_simulated_adapter.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
