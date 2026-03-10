from _compat import execute, reexport

_TARGET = "optimization/run_research_optuna.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
