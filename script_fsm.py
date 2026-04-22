import re

with open('apps/reference/domains/execution_position/fsm.py', 'r') as f:
    text = f.read()

# Remove the block
start = text.find('    def _schedule_bracket_health_check(self) -> None:')
end = text.find('    def _create_open_flow(self, symbol: str) -> OpenFlowFSM:')
text = text[:start] + text[end:]

# Replace the single call
text = text.replace('self._schedule_bracket_health_check()', 'self._bracket_health.schedule_bracket_health_check()')

# Import BracketHealth
# We find import of FillIngressCoordinator and inject it there 
if 'from .fill_ingress_coordinator import FillIngressCoordinator' in text:
    text = text.replace(
        'from .fill_ingress_coordinator import FillIngressCoordinator',
        'from .fill_ingress_coordinator import FillIngressCoordinator\nfrom .bracket_health import BracketHealth'
    )
elif 'from .bracket_ownership import BracketOwnership' in text:
    text = text.replace(
        'from .bracket_ownership import BracketOwnership',
        'from .bracket_ownership import BracketOwnership\nfrom .bracket_health import BracketHealth'
    )
else:
    # Just inject it somewhere safe before the class
    class_idx = text.find('class ExecPosFSM(')
    text = text[:class_idx] + 'from .bracket_health import BracketHealth\n\n' + text[class_idx:]

# Initialize BracketHealth
init_idx = text.find('self._fill_ingress_coordinator = FillIngressCoordinator(self)')
if init_idx != -1:
    text = text[:init_idx] + 'self._bracket_health = BracketHealth(self)\n        ' + text[init_idx:]
else:
    # Find self._bracket_ownership = BracketOwnership(self)
    bo_idx = text.find('self._bracket_ownership = BracketOwnership(self)')
    if bo_idx != -1:
         text = text[:bo_idx] + 'self._bracket_health = BracketHealth(self)\n        ' + text[bo_idx:]

with open('apps/reference/domains/execution_position/fsm.py', 'w') as f:
    f.write(text)

