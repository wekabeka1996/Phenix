from _compat import execute, reexport

_TARGET = "monitoring/obs02_ctx_log_inventory.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
