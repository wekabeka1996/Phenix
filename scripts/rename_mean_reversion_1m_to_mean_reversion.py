from _compat import execute, reexport

_TARGET = "maintenance/rename_mean_reversion_1m_to_mean_reversion.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
