from _compat import execute, reexport

_TARGET = "diagnostics/diagnose_latent.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
