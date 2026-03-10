from _compat import execute, reexport

_TARGET = "maintenance/autofill_config_defaults_into_yaml.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
