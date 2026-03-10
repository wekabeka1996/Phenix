from _compat import execute, reexport

_TARGET = "maintenance/rescue_brain.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
