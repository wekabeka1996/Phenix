# TASK27.3 — DomainConfigResolver Zombie Check

## Claim
“`DomainConfigResolver` is a zombie abstraction (dead/unused), redundant vs direct `config.domains.*` access.”

## Status
DISPROVED (it’s live runtime code)

## Evidence (where it is used at runtime)

### Runtime call sites
- `apps/reference/main.py:107` — constructs resolver in `AuroraBridge.__init__` and reads canonical domain config: `resolver.get_position_tracking().positions_stale_ttl_sec`.
- `apps/reference/domains/decision_making/decision_making.py:210` — constructs resolver; uses `resolver.get_decision_making()` for QoS + position sizing.
- `apps/reference/domains/execution_position/exposure_guard.py:94` — constructs resolver; uses `resolver.get_exposure_guard()` for limits/TTLs.
- `apps/reference/domains/position_tracking/position_tracking.py:70` — uses resolver to read `domains.position_tracking.*` settings.
- `apps/reference/domains/account_observer/account_observer.py:95` — uses resolver to read `domains.account_observer.*` settings.
- `apps/reference/domains/risk_management/risk_management.py:64` — stores `self.resolver = DomainConfigResolver(config)` and reads `resolver.get_risk_management()`.

### “Not zombie” enforcement (usage is explicitly policy-gated)
- `tests/runtime/test_no_new_domain_resolver_usage.py:9` — AST policy-gate: resolver usage is allowlisted to a fixed set of files; new usages fail CI.

## Notes
- `DomainConfigResolver` is not the only way configs are accessed, but it is an active runtime dependency in multiple domains and in `apps/reference/main.py`.
- The resolver is fail-closed by design (requires `config.domains`), so it enforces canonical domain config loading rather than being a no-op wrapper.

