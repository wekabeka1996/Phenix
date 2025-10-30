import sys

sys.path.insert(0, ".")
sys.path.insert(0, "vfoundation")
from vfoundation.apps.reference.domains.execution_position.test_order_index import (
    TestOrderIndex,
)
import unittest

# Run tests
suite = unittest.TestLoader().loadTestsFromTestCase(TestOrderIndex)
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
print(
    f"Tests run: {result.testsRun}, Failures: {len(result.failures)}, Errors: {len(result.errors)}"
)
