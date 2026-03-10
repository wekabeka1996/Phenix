from _compat import execute, reexport

_TARGET = "calibration/calibrate_md_amr_weights.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
