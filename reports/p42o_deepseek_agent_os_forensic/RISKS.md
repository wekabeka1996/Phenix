# Risks

This report maps the operational risks identified during the forensic audit.

## 1. Memory Collisions
- **Risk**: Attempting to run Target A concurrently with Target B/C will result in duplicate session folders and file write conflicts.
- **Mitigation**: Keep Target A Express server stopped during P42 runs.

## 2. Inconsistent Configurations
- **Risk**: Conflicting ports and URLs in `.env` (e.g., `PHENIX_SHADOW_API_URL` pointing to localhost instead of the active testnet endpoint).
- **Mitigation**: Strict validation of environment variables prior to session initialization.
