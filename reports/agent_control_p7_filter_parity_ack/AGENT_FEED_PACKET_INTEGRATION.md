# AgentFeedPacket integration

The readiness publication owns full `FilterParityAcknowledgementV0` records. Requested-symbol projection copies only compact `FilterParityAckSummaryV0` rows into `execution_body.filter_parity_acknowledgements`:

- symbol;
- parity status and severity;
- acknowledgement status;
- review flag;
- compatibility summary;
- raw/history refs.

Full values and history never expand the packet. All ten observed packets contained exactly BTCUSDT and ETHUSDT parity summaries and remained below budget without omission.
