from _compat import execute, reexport

_TARGET = "forensics/pending_entry_counterfactuals.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
