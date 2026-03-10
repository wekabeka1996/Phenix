from _compat import execute, reexport

_TARGET = "runners/run_alpha_search_domain.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
