from _compat import execute, reexport

_TARGET = "simulation/neocortex_shadow_simulator.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
