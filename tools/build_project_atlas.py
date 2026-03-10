from _compat import execute, reexport

_TARGET = "docs_gen/build_project_atlas.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
