from _compat import execute, reexport

_TARGET = "tmp/tmp_neocortex_runtime_report.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
