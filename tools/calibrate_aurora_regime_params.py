from _compat import execute, reexport

_TARGET = "calibration/calibrate_aurora_regime_params.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
