from _compat import execute, reexport

_TARGET = "ci_cd/validate_configs.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
