from _compat import execute, reexport

_TARGET = "diagnostics/check_orders.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
