from _compat import execute, reexport

_TARGET = "data/data_converter.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
