# Operator acknowledgement model design

The accepted offline file is a bounded manifest of `OperatorParityAcknowledgementInputV0` entries. Every entry requires:

- schema and unique ack id;
- explicit operator id and optional display name;
- created, expires, and review-required-by timestamps;
- symbol, venue, environment, exact state ref;
- parity and compatibility claims;
- one allowed acknowledgement status;
- non-empty review reason;
- explicit offline-file provenance metadata.

`OperatorParityAcknowledgementV0` is produced only after load and adds normalized file hash, validation status/reason, file ref, loaded timestamp, and the matching runtime state ref.

Identity is never inferred from the OS. Acknowledgement is descriptive review metadata, never permission to trade.
