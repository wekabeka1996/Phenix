# UNMATCHED_CLASSIFICATION

Generated at UTC: 2026-05-10T19:14:13.915648+00:00

Audit source kind: artifact_authority_snapshot
Source snapshot manifest: artifacts/calibration_datasets/_post_03k_realized_outcome_03q/source_snapshot/source_snapshot_manifest.json

## Counts

| classification | count |
| --- | --- |
| NOT_EXECUTED_OR_REJECTED | 75 |
| ENTRY_SUBMITTED_NOT_FILLED | 0 |
| ENTRY_FILLED_POSITION_STILL_OPEN | 0 |
| CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | 1 |
| CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | 0 |
| CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | 12 |
| REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | 0 |
| LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 0 |
| TRADE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 0 |
| BUILDER_CANONICALIZATION_GAP | 0 |
| SOURCE_LOGGING_GAP | 0 |
| INCONCLUSIVE | 1 |

## Warnings

- none

## Decisions

| decision_id | rid | classification | classification_reason |
| --- | --- | --- | --- |
| 0312e43e-99ff-4a7e-81d9-06e9e3a3f177 | aurora_BNBUSDT_1778377202278 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| a95253fd-064c-4400-865d-ac2a4326b7ae | aurora_BNBUSDT_1778378405537 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 9476911e-0b0d-48a8-aaa5-af9066d21f38 | aurora_BNBUSDT_1778379004957 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| f08eb9b1-3e75-4c29-ab86-baa26ec7c19d | aurora_BNBUSDT_1778405705080 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 45392f14-62a8-4b49-949b-060a4da5005c | aurora_BNBUSDT_1778416502994 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 5abb180a-88ee-465c-a9c8-2b39199963cf | aurora_BTCUSDT_1778364903981 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 175b9a3b-136e-4afe-8a96-bcd3ce62d151 | aurora_BTCUSDT_1778365504313 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 352960c3-75b9-4ed7-8080-096ca3d72b58 | aurora_BTCUSDT_1778423406340 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| fc6c34fe-8e18-4a07-80b9-1594f784d93d | aurora_BTCUSDT_1778424001517 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a6910d76-9f20-4ec4-a0ca-c343c1eedd36 | aurora_BTCUSDT_1778424602438 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| b2ba9f23-ab08-4bd5-a346-373171506fde | aurora_BTCUSDT_1778429706498 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 75dbedd2-9fb4-4c73-add2-3b7592bb863b | aurora_ETHUSDT_1778364903614 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9c018e52-d657-4c59-8061-e03bc9d4817b | aurora_ETHUSDT_1778365504159 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 832093a0-386c-4b10-aac0-bd98d686802d | aurora_ETHUSDT_1778366700990 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b12e06f9-4c24-4237-8b76-194080c494ff | aurora_ETHUSDT_1778367902859 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 93b9d629-02d9-405f-bd59-fc241ceaedb0 | aurora_ETHUSDT_1778368503976 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 03785993-d89e-4e3a-980e-7621247d905b | aurora_ETHUSDT_1778369104713 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d2b20ea9-84f3-4174-889e-1cb245c20925 | aurora_ETHUSDT_1778369700516 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0aa8a0b7-18bd-417f-a785-a7e4a9227495 | aurora_ETHUSDT_1778370301532 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0ff20078-141a-45d8-9186-196126bfda0d | aurora_ETHUSDT_1778370902296 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2a753fce-fab1-4f2d-b151-fad2157ed9b1 | aurora_ETHUSDT_1778371502977 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 930668d3-6cd1-4db9-b392-e914c578ee82 | aurora_ETHUSDT_1778372103971 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 512a9712-7717-43d2-b0a9-332dae49bfbf | aurora_ETHUSDT_1778372704560 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 48c36140-73bd-4fa0-bd6c-6c3acd951a18 | aurora_ETHUSDT_1778373300495 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8a8850b7-9322-4540-ad30-5be8da9cf9e0 | aurora_ETHUSDT_1778373901702 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e3a715c9-7a29-4a28-b316-de5569776e1f | aurora_ETHUSDT_1778375103490 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8e5d924f-be85-4b44-914f-09715ee34e89 | aurora_ETHUSDT_1778375704628 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 176bfc46-3ce5-41e2-b4a5-29ac9a1d63a7 | aurora_ETHUSDT_1778376305178 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c832a6d4-ab42-4e5a-9e27-a68c7a4a2ed8 | aurora_ETHUSDT_1778376901042 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 88911d48-1f7e-4338-8ec6-e5e3cd691126 | aurora_ETHUSDT_1778377502081 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| dfddaf21-dfb4-4612-87af-8925ff787a72 | aurora_ETHUSDT_1778378102890 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9276b39d-5918-4f5d-8ad8-07ba3b7c3511 | aurora_ETHUSDT_1778379304878 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8ef68a7f-9ee9-495c-be31-1b43269b1b18 | aurora_ETHUSDT_1778379900622 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4def11c7-e102-44de-8b45-f601be5448eb | aurora_ETHUSDT_1778382304145 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 02a25733-5554-4c5a-bdfa-3777af13318c | aurora_ETHUSDT_1778382905385 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a445c858-85ff-43ca-963d-e3843b1dcede | aurora_ETHUSDT_1778383205376 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c4545766-a092-4274-9b24-29f86a358b76 | aurora_ETHUSDT_1778383801680 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| dda0a8d6-4dd3-4ce0-a3b3-5c1f4baf8362 | aurora_ETHUSDT_1778384101718 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 249bf4d0-477e-4a61-9106-33cbdaafa4e3 | aurora_ETHUSDT_1778386505884 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1d362730-af67-44e1-bb56-d0bc62db4805 | aurora_ETHUSDT_1778387101317 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2b411825-0584-4500-9e50-b4dfcfa330ba | aurora_ETHUSDT_1778387702230 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8d74dbbc-8c92-4ac3-8c3a-4e92da4761cd | aurora_ETHUSDT_1778388303535 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 68f98cbe-8a47-41b6-8828-646aa9d2a296 | aurora_ETHUSDT_1778388904018 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f32dfef2-bc82-47b8-bed6-f47f3cd9db75 | aurora_ETHUSDT_1778389504961 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8ebd44bd-38ee-4667-85a0-3b68f4925a9b | aurora_ETHUSDT_1778390101143 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e3fe2e20-769a-4a06-a2f0-2631ff210f5b | aurora_ETHUSDT_1778390701640 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 66239d74-2f1b-4592-93b0-7421885ad9fd | aurora_ETHUSDT_1778391302578 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| fc2be55d-9bb8-42ba-b975-701072f4a3b7 | aurora_ETHUSDT_1778393105140 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1eabc5ff-3780-4977-9a0e-9d81a0f2a26f | aurora_ETHUSDT_1778393701240 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2cfd5cb6-9c79-4b16-afc8-b642b3807e09 | aurora_ETHUSDT_1778394902464 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ca826557-5404-427d-8782-dc9c24dd5d05 | aurora_ETHUSDT_1778395503519 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1dc61e00-caae-499c-8bab-620343254859 | aurora_ETHUSDT_1778396104002 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| eeac9c89-1e83-4c4a-8608-9261b470583e | aurora_ETHUSDT_1778396704850 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 875958dd-3169-4aa8-a847-c2df4672fbb3 | aurora_ETHUSDT_1778397601285 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d2f035d6-9446-40e6-9a3a-62487620316b | aurora_ETHUSDT_1778398202464 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5b02d05e-61aa-4ef6-a12f-459581bae697 | aurora_ETHUSDT_1778400305385 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 31ea7b55-2015-4346-b78a-ca9b74190e9d | aurora_ETHUSDT_1778400901679 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9fc4fc9b-9e82-47ba-9009-6ac284413f68 | aurora_ETHUSDT_1778401502903 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 107dafa9-373e-495f-bc78-381917e3a464 | aurora_ETHUSDT_1778403005088 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4122a613-676c-41e3-babe-d5f53a531e42 | aurora_ETHUSDT_1778404202008 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bb795500-79e5-49f6-b5b0-fc1d3a60687f | aurora_ETHUSDT_1778406600644 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c291335e-ba46-4836-89c0-6031393f7b18 | aurora_ETHUSDT_1778407201852 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f34b036c-b5b3-4c07-a0f3-e0734c6755e0 | aurora_ETHUSDT_1778413202076 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5f6eb409-2d21-4ea5-bd97-b57ee1eb9403 | aurora_ETHUSDT_1778413802871 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 828ebe90-fe22-4a71-a7f9-462586e6439f | aurora_ETHUSDT_1778414404411 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e6adbdb4-c813-463f-b0d3-ca67862bffce | aurora_ETHUSDT_1778415004660 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 066e1ee9-744c-4416-9695-5a05ab8686be | aurora_ETHUSDT_1778415600748 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8810f038-e022-4797-9333-7587926d96ab | aurora_ETHUSDT_1778416202193 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5717d369-9401-4067-aa1c-686ced97b813 | aurora_ETHUSDT_1778417103171 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5e809e07-8d17-4298-85a6-3d50388d1986 | aurora_ETHUSDT_1778417703600 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b95c25f9-2186-43ff-a774-ba3c903413d8 | aurora_ETHUSDT_1778418304492 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f85ba24a-7357-4a93-a55c-579ebd1939da | aurora_ETHUSDT_1778418906013 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2c0975f3-b84b-48a9-adbb-8a99722b0675 | aurora_ETHUSDT_1778422803971 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3397534e-71a0-43d4-a233-845d69a8281e | aurora_ETHUSDT_1778423405632 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c4aa414a-940f-49b9-93eb-a5bac1620279 | aurora_ETHUSDT_1778428202947 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| bc29ea0a-be2a-4859-bc8c-3a3aa4de5d6e | aurora_XRPUSDT_1778375104123 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 962df9c0-5524-4c77-84cf-c674dd862398 | aurora_XRPUSDT_1778375705811 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3b8dc243-e2cb-4e21-8faf-cdfbe1fc1035 | aurora_XRPUSDT_1778376305663 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 35558a53-2a9c-4f48-aa0e-e346344319d3 | aurora_XRPUSDT_1778376901653 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| df877b80-3d1d-4e8a-a5de-f94dba6e6f5f | aurora_XRPUSDT_1778377502943 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4200ccbc-ad87-45d0-8549-dfa05af6023e | aurora_XRPUSDT_1778378103489 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5e1ce104-a33f-49e0-9946-420ee2c5dfb5 | aurora_XRPUSDT_1778378704419 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a82c414d-7d23-4b3c-8d94-cc1b2f6ba69c | aurora_XRPUSDT_1778379306308 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4f2bcf1c-c0d3-4af7-8a2f-1b18e8a57570 | aurora_XRPUSDT_1778379901156 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f86d4702-0060-44fa-8b0c-f60959b90dd3 | aurora_XRPUSDT_1778382005365 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 3b08ec21-e398-4a47-bf90-bfcfc64d94af | aurora_XRPUSDT_1778402706854 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| e806c966-ada3-40ce-a46f-ebb6979e28bf | aurora_XRPUSDT_1778414705236 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 844759bd-cafb-4842-a8e4-0645d416359c | aurora_XRPUSDT_1778430903673 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| b6acf83d-533c-4607-87fb-9cf01c59ce83 | mdamr-46e01379f472b1c7 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
