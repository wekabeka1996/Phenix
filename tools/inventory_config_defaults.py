from _compat import execute, reexport

_TARGET = "ci_cd/inventory_config_defaults.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
