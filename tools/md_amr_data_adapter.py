from _compat import execute, reexport

_TARGET = "simulation/md_amr_data_adapter.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
