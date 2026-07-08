# Risks

- No browser UI wiring exists in this package; future UI work must call the new routes explicitly.
- No direct binary upload is implemented; image/file support is metadata/ref based only.
- ContextBuilder uses a fixed attachment prompt budget of min(artifact_budget_chars, 12000) because no attachment-specific config exists yet.
- Attachment deletion/update/versioning is not implemented.
- Attachment records are local filesystem JSON files; concurrent writes rely on the existing atomic write helper but there is no higher-level index lock.
