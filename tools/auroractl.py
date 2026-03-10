from _compat import execute, reexport

_TARGET = "cli/auroractl.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
