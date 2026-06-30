# P6 recommendation

Implement a credential-free, public exchange-info observation owner that:

- fetches only public filter metadata;
- publishes source timestamp and freshness;
- compares exchange values against typed config without mutating either;
- never shares an order adapter or credential surface;
- keeps config-only state degraded until fresh parity is observed;
- preserves the no-order composition and GET-only Cockpit bridge.

Do not add AgentIntent, dry-run execution, order routing, policy bypasses, or action controls.
