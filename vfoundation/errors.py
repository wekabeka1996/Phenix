"""
Phenix error taxonomy for structured exception handling.

Additive implementation: small, non-breaking error classes to standardize handling.
"""


class PhenixError(Exception):
    """Base class for all Phenix errors."""
    pass


class ConfigError(PhenixError):
    """Configuration parsing or validation error."""
    pass


class AdapterError(PhenixError):
    """Base class for exchange adapter errors."""
    pass


class AdapterTransientError(AdapterError):
    """Transient adapter error (network timeout, -1021 time sync)."""
    pass


class AdapterRateLimitError(AdapterError):
    """Rate limit exceeded (-1003, -418)."""
    pass


class AdapterFatalError(AdapterError):
    """Permanent adapter error (bad symbol, invalid API key)."""
    pass


class DataIntegrityError(PhenixError):
    """Data validation or integrity check failed."""
    pass


class FSMError(PhenixError):
    """Finite State Machine logic error."""
    pass


class FSMStateError(FSMError):
    """Invalid FSM state transition."""
    pass


class QuickProfitError(PhenixError):
    """Quick profit logic error."""
    pass


class FallbackExhaustedError(PhenixError):
    """All price sources (MARK/LAST/MID) returned None."""
    pass


class CacheError(PhenixError):
    """Cache corruption or invariant breach."""
    pass
