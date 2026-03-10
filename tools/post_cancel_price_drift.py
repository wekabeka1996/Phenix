from _compat import execute, reexport

_TARGET = "forensics/post_cancel_price_drift.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
