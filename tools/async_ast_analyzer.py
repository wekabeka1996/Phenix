from _compat import execute, reexport

_TARGET = "analysis/async_ast_analyzer.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
