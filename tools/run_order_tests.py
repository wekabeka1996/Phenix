import sys, os

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "vfoundation"))

# Import the test class
from apps.reference.domains.execution_position.test_order_index import TestOrderIndex

# Create test instance and run methods
test_instance = TestOrderIndex()
methods = [m for m in dir(test_instance) if m.startswith("test_")]

print(f"Running {len(methods)} tests...")
passed = 0
failed = 0

for method_name in methods:
    try:
        print(f"Running {method_name}...", end=" ")
        method = getattr(test_instance, method_name)
        method()
        print("PASSED")
        passed += 1
    except Exception as e:
        print(f"FAILED: {e}")
        failed += 1

print(f"Results: {passed} passed, {failed} failed")
