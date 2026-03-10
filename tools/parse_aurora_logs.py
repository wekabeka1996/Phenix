from _compat import execute, reexport

_TARGET = "monitoring/parse_aurora_logs.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
