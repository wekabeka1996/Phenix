from _compat import execute, reexport

_TARGET = "ci_cd/audit_yaml_loading.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
