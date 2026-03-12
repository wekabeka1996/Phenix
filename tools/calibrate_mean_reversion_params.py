from _compat import execute, reexport

_TARGET = "calibration/calibrate_mean_reversion_params.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
