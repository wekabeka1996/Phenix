# TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01: Reachability Report

## 1. Reference Hits Table

| File | Line | Type | Context |
|---|---|---|---|
| `apps/reference/main.py` | 28 | **Import** | `from apps.reference.domains.account_observer.account_observer import AccountObserver` |
| `apps/reference/main.py` | 1393 | **Instantiate** | `account_observer = AccountObserver(fsm, config_dict)` (Likely legacy block or dup) |
| `apps/reference/main.py` | 1543 | **Instantiate** | `account_observer = AccountObserver(...)` (Main bootstrap) |
| `apps/reference/main.py` | 1757 | **Call** | `account_observer.start()` |
| `apps/reference/main.py` | 1850 | **Reference** | Shutdown list: `"account_observer"` |
| `apps/reference/config_models.py` | 2228, 2309 | **Config** | `AccountObserverConfig` definitions |
| `tools/verify_config.py` | 16 | **Tooling** | Checks `observer_cfg` |
| `tests/integration/test_observer_isolation.py` | 4, 43 | **Test** | Explicitly tests isolation logic |

## 2. Reachability Conclusion

**Status:** ❌ **REACHABLE** (Technically) -> but **FUNCTIONALLY DEAD** (for Futures).

The class `AccountObserver` is imported, instantiated, and started in `apps/reference/main.py`. However, internal logic within `AccountObserver.__init__` conditionally disables itself:

```python
if market_type == "futures":
    # ...
    self.logger.info("AccountObserver DISABLED (market_type='futures')...")
    return
```

Since the system is currently running in Futures mode (implied by user context and `account_connector` priority), this component acts as a "Zombie" — wired but doing nothing except checking a config flag to die.

## 3. Action Plan (Phase B)

To proceed with deletion, we must first **Unwire** it from the application root:

1.  **Unwire `main.py`**: Remove import, instantiation, registration, and start calls.
2.  **Clean Configs**: Remove `AccountObserver` sections from `config_models.py` (if verified unused by others) and `domain_config.py`.
3.  **Remove Files**: Delete `apps/reference/domains/account_observer/`.
4.  **Remove Dependency**: `python-binance` is only used here (and in its tests). Remove from environment if possible (though I cannot run `pip uninstall` on user env, I can note it).

This confirms the intent to treat it as "Dead Code" and proceed with surgical removal.
