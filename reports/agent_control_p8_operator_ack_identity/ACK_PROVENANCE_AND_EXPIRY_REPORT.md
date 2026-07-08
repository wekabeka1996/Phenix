# Acknowledgement provenance and expiry report

The loader accepts at most 64 KiB, validates the manifest before hashing, and hashes canonical JSON (`sort_keys`, compact separators). The example file normalizes to SHA-256 `5a2a956a757701b694f89070285fcf72ca4b5eaa75bda6bcb42997d1c65e812d`.

Computed provenance contains:

- opaque acknowledgement file ref with SHA-256 fragment;
- normalized SHA-256;
- load timestamp;
- expected/matching state ref;
- authored provenance and optional detached-signature placeholder.

Whitespace changes preserve the hash; semantic changes do not. Expiry is the earlier of `expires_ts_ms` and `review_required_by_ts_ms`. Conservative lifetime above 30 days is invalid. Exact-state mismatch is surfaced as `expired/state_mismatch`, not silently reused.

No cryptographic signature verification or secret key handling is implemented.
