from _compat import execute, reexport

_TARGET = "forensics/forensic_analysis.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
