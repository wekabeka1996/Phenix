# UNMATCHED_CLASSIFICATION

Generated at UTC: 2026-05-07T18:54:12.541850+00:00

Audit source kind: artifact_authority_snapshot
Source snapshot manifest: artifacts/calibration_datasets/_smoke_03j_realized_outcome/source_snapshot/source_snapshot_manifest.json

## Counts

| classification | count |
| --- | --- |
| NOT_EXECUTED_OR_REJECTED | 22 |
| ENTRY_SUBMITTED_NOT_FILLED | 0 |
| ENTRY_FILLED_POSITION_STILL_OPEN | 0 |
| CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | 0 |
| CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | 2 |
| CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | 1 |
| REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | 10 |
| LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 3 |
| TRADE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 0 |
| BUILDER_CANONICALIZATION_GAP | 0 |
| SOURCE_LOGGING_GAP | 6 |
| INCONCLUSIVE | 11 |

## Warnings

- none

## Decisions

| decision_id | rid | classification | classification_reason |
| --- | --- | --- | --- |
| 2518ba5f-191d-4569-9683-cd3202e1f9d1 | aurora_BNBUSDT_1778117100696 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| d9ed9b47-dba3-41bd-bbd6-ae1a1413d7bf | aurora_BNBUSDT_1778118303655 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| 7de55ad9-87dd-4d1e-88f7-a8ed6fec97ce | aurora_BNBUSDT_1778135105795 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 7a26fa29-4957-49b1-b609-49c8783c00da | aurora_BNBUSDT_1778137205550 | CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | close evidence exists only under a suffix alias rid |
| 800e8b0c-7e90-400d-a8ed-3f8c83444ab3 | aurora_BNBUSDT_1778142301881 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| f9ad01d3-ac77-459c-99dc-15eea7c4b5a7 | aurora_BNBUSDT_1778150105799 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| a377508e-4c7a-44de-901b-54e2b036b078 | aurora_BNBUSDT_1778157305530 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| be161de0-e6f0-42dc-82bc-743010eac0df | aurora_BNBUSDT_1778157908176 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f8ef190f-c229-4b6a-bed0-67bbdba28332 | aurora_BNBUSDT_1778175906312 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| 86cd3355-b95e-43a7-9fad-c71a31edaca5 | aurora_BTCUSDT_1778118302649 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 93b7a545-9c57-456f-9f53-c321f492b9d6 | aurora_BTCUSDT_1778118903181 | CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | close evidence exists only under a suffix alias rid |
| 17c5aaa1-9f25-4da3-899a-982ac1f8e468 | aurora_BTCUSDT_1778130003092 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| 4d4daf55-3ec4-4bd0-921b-091b0663ab4e | aurora_BTCUSDT_1778133002307 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e0ad48f7-c730-4aa8-99b3-f983f126e945 | aurora_BTCUSDT_1778133603736 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 67ed9b02-5588-409b-b81e-95a5791101ee | aurora_BTCUSDT_1778134203982 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d5cc9e4e-6424-4e54-a219-4237171762c2 | aurora_BTCUSDT_1778136002120 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| e5e97dc2-c23a-46e5-bf5c-e6fac9544e7d | aurora_BTCUSDT_1778136602978 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f47914ea-1806-46cb-abbd-b8f38685c998 | aurora_BTCUSDT_1778137204168 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 45552229-2f46-4f3a-89e7-fef50eb0760a | aurora_BTCUSDT_1778137804789 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 223bf33b-d9e7-4b63-90e1-fd285e432b08 | aurora_BTCUSDT_1778140805090 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3688bbba-3114-447f-b2a7-ef6d03acf3d8 | aurora_BTCUSDT_1778146502686 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| 5b60266c-fff8-4c55-a68b-3349dda27e4c | aurora_BTCUSDT_1778147104499 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| 2917dd30-8c60-4d82-9dd5-b03deb66b269 | aurora_BTCUSDT_1778147404143 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e210bee4-2f5b-48d4-b34a-e858e9e91d6f | aurora_BTCUSDT_1778148005784 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bffac47a-52dc-4dcd-b477-6809e220ee95 | aurora_BTCUSDT_1778159103180 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 614fb12c-efe1-4340-a0b8-4d0e2d6d42ad | aurora_BTCUSDT_1778159704993 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d5343e33-fa25-4228-a0ac-24a5991f0e07 | aurora_BTCUSDT_1778160305157 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 28e168b6-7947-4bf5-a670-930195c6141a | aurora_BTCUSDT_1778160901236 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e2b8affd-210e-4f92-a5ad-ee3581008c2f | aurora_BTCUSDT_1778161503220 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 68b60e09-11d8-4b17-baf0-17433129b03b | aurora_BTCUSDT_1778161803308 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 0969529d-71cb-400e-bce3-359324761cd5 | aurora_BTCUSDT_1778164800612 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| 036ebb69-30bd-461e-9eda-325bef3fb97c | aurora_ETHUSDT_1778132702038 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6a9934cf-b6fd-48fa-aa72-ec5b4668628d | aurora_ETHUSDT_1778133903478 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a86d2d94-9501-4417-bd91-38d6408202fb | aurora_ETHUSDT_1778149803722 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 41c10df9-cae0-48e8-ad45-3fa8b4495149 | aurora_ETHUSDT_1778161802833 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| fe0a2770-1a21-4781-b0bb-8e8e0ebcfdf6 | aurora_ETHUSDT_1778163005891 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 86dbec40-8465-4b29-a245-e53ec18904fb | aurora_ETHUSDT_1778164505045 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| ccce18ec-8c68-47dc-8396-33f269980dc3 | aurora_ETHUSDT_1778166604942 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| 2e226861-c046-4f10-ac1d-715abfacfdc1 | aurora_ETHUSDT_1778167809797 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| 20113748-1eb5-4495-83c1-0d6ba06a4ca0 | aurora_ETHUSDT_1778169005752 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| a2c62039-4127-4a0d-8e82-aa91f434eaed | aurora_ETHUSDT_1778170508967 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| a9c3df7e-6a72-49b9-8082-64bfeb8ca772 | aurora_ETHUSDT_1778172006630 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 9af22e74-4883-4d40-98a7-2193424b4a67 | aurora_SOLUSDT_1778172602326 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| b6a190af-786b-4efa-aa5f-3f017cd07652 | aurora_XRPUSDT_1778123703440 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4ebe9a57-dbcd-41c0-b676-57bf4c5badc1 | aurora_XRPUSDT_1778124303469 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 38728134-9dd7-4fee-bbf5-d1f8b59dc23a | aurora_XRPUSDT_1778128505414 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 191c6ea6-8026-4cfe-80e3-826916b7fcda | aurora_XRPUSDT_1778143203235 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| efadb488-7cff-4c8a-a67a-2275fd6d987d | aurora_XRPUSDT_1778149202358 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| 88802dda-4c05-4e3b-b810-8776570a5968 | aurora_XRPUSDT_1778150105378 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 46954944-8693-4582-be46-51b836a3ecd6 | aurora_XRPUSDT_1778151301466 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| b571442a-8fbf-47c9-848b-f5ebbe2cc817 | aurora_XRPUSDT_1778161803930 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| f522cd00-4eed-4106-a824-7c5a6b41dfab | aurora_XRPUSDT_1778162705894 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 61986c5d-2d95-4c26-ae4c-b0d388d10948 | aurora_XRPUSDT_1778164505506 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| ebbd1db9-cd2c-42ad-a553-c1326734eccd | aurora_XRPUSDT_1778169008119 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| ae9cb531-912e-4797-875f-d04af441df64 | aurora_XRPUSDT_1778172009633 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
