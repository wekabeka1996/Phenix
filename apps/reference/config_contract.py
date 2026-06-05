
class ConfigContractError(RuntimeError):
    """
    Raised when a configuration violates the strict SSOT contract.
    
    This replaces generic ValueErrors for P1 critical configuration checks (Instrument Overrides, Risk Limits).
    It guarantees a fail-closed behavior upstream by signaling a specific contract violation.
    
    Attributes:
        path (str): The config path/key that caused the error (e.g. 'strategies.aurora.assets.BTCUSDT.max_risk_score').
        symbol (str, optional): The symbol context if applicable.
        why (str): Human readable reason for the violation.
    """
    def __init__(self, path: str, why: str, symbol: str = None):
        self.path = path
        self.symbol = symbol
        self.why = why
        ctx = f"[{symbol}] " if symbol else ""
        super().__init__(f"CONFIG_CONTRACT_VIOLATION: {ctx}Path='{path}' Reason='{why}'")
