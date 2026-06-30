# Atomic publication validation

The store writes compact schema-valid JSON to a same-directory temporary file, flushes/fsyncs, replaces the fixed target atomically, retries transient Windows replace contention, and leaves no temporary residue.

Live validation:

- 40 read-host packet polls ran across a natural market file update;
- market mtime changed from 12:06:00 to 12:09:01 during the loop;
- HTTP/schema success: 40/40;
- direct ownership: 40/40;
- failures/partial reads: 0;
- `.tmp` residue: 0;
- read latency: 13.54-85.27 ms.

Unit tests also cover atomic write/read, invalid JSON rejection, oversize rejection, and no temp residue. Natural JSONL rotation was not forced and is non-blocking.
