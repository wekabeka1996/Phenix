# TASK27 — CONFIG & ARCHITECTURE CLAIMS VERIFICATION (Final Verdict)

| Claim | Status | Evidence | Risk |
| --- | --- | --- | --- |
| Optional + Field() ⇒ Field required (Pydantic v2 trap) | ✅ CONFIRMED (trap exists); no current startup failure observed | `reports/TASK27_optional_field_required_audit.md` | P1 |
| `TradingConfig.risk: Dict[str, Any]` breaks object-access | ◐ PARTIAL (is dict; runtime uses dict-access w/ type checks) | `reports/TASK27_trading_risk_type_audit.md` | P2 |
| DomainConfigResolver is zombie abstraction | ❌ DISPROVED (active runtime dependency; usage policy-gated) | `reports/TASK27_domain_resolver_status.md` | P2 |
| ConfigLoader hydration/setdefault is schema workaround | ✅ CONFIRMED (pre-validation mutations to satisfy schema + migrations) | `reports/TASK27_loader_hydration_audit.md` | P1 |
| Global config via `config_symbols.py` | ◐ PARTIAL (singleton exists in `config_loader`; `config_symbols` is a thin wrapper) | `reports/TASK27_global_config_audit.md` | P1 |
| `.to_dict()` is an architectural hole | ◐ PARTIAL (`AuroraConfig.to_dict()` exists; runtime domains guarded by AST gates) | `reports/TASK27_to_dict_surface_audit.md` | P2 |

