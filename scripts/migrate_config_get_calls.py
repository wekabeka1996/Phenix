from _compat import execute, reexport

_TARGET = "maintenance/migrate_config_get_calls.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
