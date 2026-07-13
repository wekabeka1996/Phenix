# Context Reader

## FACTS

Required fields are manifest version, instruction version, timestamps, bounded critical/unresolved items, and source references.

Production Aurora main owns none of these as a coherent object. `TradingSession.instruction_version` supplies only one field. DecisionMaking market snapshots are not a context manifest. Terminal-agent `CanonicalMemoryStore` is constructed in a different process with its own explicit storage configuration.

## Decision

No adapter was added. Reading reports/logs, Cockpit SQLite, or inventing a JSON projection would violate the task. Instantiating a second writable memory store in main would risk dual authority.

Required predecessor: approve and expose one read-only canonical context projection contract from the actual writer, including version-change publication and source references.
