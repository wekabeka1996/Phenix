from _compat import execute, reexport

_TARGET = "simulation/synthetic_llm_intent_generator.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
