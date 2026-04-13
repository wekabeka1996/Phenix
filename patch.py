import re

with open('apps/reference/domains/feature_engineering/feature_engineering.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_text = '''        self._register_listeners()
        self.logger.info(
            f"[{self.__class__.__name__}] Initialization complete. CFG-WARMUP-01: "
            f"enforcement_mode={self.cfg.warmup_enforcement_mode}"
        )'''

new_text = '''        self._register_listeners()
        self.logger.info(
            f"[{self.__class__.__name__}] Initialization complete. CFG-WARMUP-01: "
            f"enforcement_mode={self.cfg.warmup_enforcement_mode}"
        )

    def _is_degraded_allowed_for_symbol(self, symbol: str) -> bool:
        """
        Check if the symbol's ENTIRE assigned strategy set is explicitly degraded-eligible.
        """
        degraded_allowed = getattr(self.cfg._cfg.warmup, 'degraded_allowed_strategies', [])
        if not degraded_allowed:
            return False

        registry = getattr(self, '_resolver', None)
        if registry:
            registry = registry.get_strategies_registry()
        if not registry:
            return False

        assigned_strats = registry.assignments.get(symbol, [])
        if not assigned_strats:
            return False

        for strat in assigned_strats:
            if strat not in degraded_allowed:
                return False

        return True'''

if old_text in text:
    text = text.replace(old_text, new_text)
    with open('apps/reference/domains/feature_engineering/feature_engineering.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print('PATCHED')
else:
    print('Pattern not found.')
