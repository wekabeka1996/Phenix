from _compat import execute, reexport

_TARGET = "docs_gen/generate_config_map.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
