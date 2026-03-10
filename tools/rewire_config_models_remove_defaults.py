from _compat import execute, reexport

_TARGET = "maintenance/rewire_config_models_remove_defaults.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
