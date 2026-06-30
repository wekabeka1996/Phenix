# Token budget report

P4 packets used 2,824 estimated tokens. P5 packets used 3,613-3,614 of the 4,400 cap, approximately 82.1% utilization and 786 tokens of minimum headroom.

Payload size was 14,450-14,453 bytes. All ten packets reported `truncated=false`.

Budget controls:

- readiness publication may cover all configured symbols;
- packet projection retains only requested symbol descriptors plus three global reduce-only descriptors;
- the optional full readiness snapshot is not duplicated inside `ExecutionBodyCard`;
- opaque refs replace raw owner objects.
