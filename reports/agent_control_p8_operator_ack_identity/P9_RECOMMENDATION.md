# P9 recommendation

Add dependency-light detached-signature verification for offline acknowledgements:

- map trusted operator ids to public verification keys in a separate governance config;
- sign canonical acknowledgement content outside Aurora;
- verify without reading private keys or secrets;
- record signer key id and verification result in provenance;
- provide a read-only lint/inspect command before file deployment.

Keep P9 separate from YAML mutation, AgentIntent, order routing, Cockpit actions, and all execution authority.
