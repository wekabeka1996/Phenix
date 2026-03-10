from _compat import execute, reexport

_TARGET = "diagnostics/validate_testnet.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
