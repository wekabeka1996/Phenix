from _compat import execute, reexport

_TARGET = "calibration/calibrate_aurora_signal_weights.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
