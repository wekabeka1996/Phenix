import ast

extracted_modules = [
    'apps/reference/domains/execution_position/position_policy_mediator.py',
    'apps/reference/domains/execution_position/bracket_ownership.py',
    'apps/reference/domains/execution_position/fill_ingress_coordinator.py',
    'apps/reference/domains/execution_position/bracket_health.py',
    'apps/reference/domains/execution_position/startup_truth_orchestrator.py',
]

for path in extracted_modules:
    try:
        with open(path, 'r') as f:
            text = f.read()
        tree = ast.parse(text)

        private_accesses = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # pattern: self._fsm._something  (private attr on back-ref)
                if (isinstance(node.value, ast.Attribute) and
                        isinstance(node.value.value, ast.Name) and
                        node.value.value.id == 'self' and
                        node.value.attr == '_fsm' and
                        node.attr.startswith('_')):
                    private_accesses.append(node.attr)

        unique = sorted(set(private_accesses))
        name = path.split('/')[-1]
        print(f'\n{name}: {len(unique)} unique private attrs accessed on self._fsm')
        for u in unique:
            print(f'  self._fsm.{u}')
    except Exception as e:
        print(f'{path}: ERROR {e}')
