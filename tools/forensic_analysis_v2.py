from _compat import execute, reexport

_TARGET = "forensics/forensic_analysis_v2.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
