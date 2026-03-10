from _compat import execute, reexport

_TARGET = "alpha_search/alpha_search_report.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
