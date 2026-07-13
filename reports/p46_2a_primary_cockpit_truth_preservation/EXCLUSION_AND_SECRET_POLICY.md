# Exclusion and Secret Policy

## FACTS

Excluded before hashing/copying content:

- `.env`, `.env.*` except reviewed `.env.example`;
- `*.key`, `*.pem`, credentials;
- `node_modules/`, `dist/`, `build/`, `coverage/`;
- `.agent_workspace/runtime_store/`, SQLite/WAL/SHM;
- logs, temporary messages/sessions, generated and machine-specific files.

Excluded files are represented by path, size, timestamp, and classification only. The active `runtime.sqlite` was not read or hashed. The 14 imported files produced no secret-like pattern hit. `.env.example` was unchanged semantically and was not imported.

## INFERENCES

The preservation commits contain no credential or runtime database material.

## ASSUMPTIONS

Pattern scanning complements, but cannot mathematically prove, absence of every possible secret encoding.

## UNKNOWNS

Contents of excluded private runtime attachments were deliberately not inspected.
