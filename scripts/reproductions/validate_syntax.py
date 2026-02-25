
import sys
import os

# Add root to python path
sys.path.append(os.getcwd())

try:
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    print("SUCCESS: DecisionMaking imported successfully.")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FAILURE: Syntax or Import Error: {e}")
    sys.exit(1)
