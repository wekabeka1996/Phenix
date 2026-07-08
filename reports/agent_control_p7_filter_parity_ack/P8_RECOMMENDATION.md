# P8 recommendation

Add operator identity and provenance around the existing file-based acknowledgement seam: signer/role, reason code, expiry policy, independent review for risky drift, and an audit command that writes only the acknowledgement file.

Do not combine P8 with automatic YAML correction, constraint relaxation, AgentIntent, execution routing, or authority enablement. Risky and stale/missing states must continue blocking any future execution authority independently of acknowledgement.
