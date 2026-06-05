# UNMATCHED_CLASSIFICATION

Generated at UTC: 2026-05-13T19:24:50.112943+00:00

Audit source kind: artifact_authority_snapshot
Source snapshot manifest: artifacts/calibration_datasets/_post_03t_multiday_realized_outcome/source_snapshot/source_snapshot_manifest.json

## Counts

| classification | count |
| --- | --- |
| NOT_EXECUTED_OR_REJECTED | 263 |
| ENTRY_SUBMITTED_NOT_FILLED | 0 |
| ENTRY_FILLED_POSITION_STILL_OPEN | 0 |
| CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | 14 |
| CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | 3 |
| CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | 20 |
| REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | 12 |
| LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 4 |
| TRADE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 0 |
| BUILDER_CANONICALIZATION_GAP | 0 |
| SOURCE_LOGGING_GAP | 3 |
| INCONCLUSIVE | 3 |

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
| a48e96d3-8a96-49bb-b6f4-adf762bff48f | aurora_BNBUSDT_1778426406618 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| aa7e825b-2e5a-4de2-a2a5-742843e94e7d | aurora_BNBUSDT_1778472302897 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| adfb3724-7d03-4063-8bd0-ce02bde23d13 | aurora_BNBUSDT_1778512805536 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 15f271c3-483f-4191-9b26-a2f8f51ddd0b | aurora_BNBUSDT_1778559903748 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 77377d40-b742-4dff-8092-210b96412618 | aurora_BNBUSDT_1778593802549 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| a7633d82-cae3-48d7-aa32-1c2bf555e1d3 | aurora_BNBUSDT_1778595005175 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 90481924-d05f-43e3-9b3e-339316d8475c | aurora_BNBUSDT_1778620205221 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| d4ad7f4e-28d4-41ee-8148-d7bd301e5303 | aurora_BNBUSDT_1778682001038 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 5abb180a-88ee-465c-a9c8-2b39199963cf | aurora_BTCUSDT_1778364903981 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 175b9a3b-136e-4afe-8a96-bcd3ce62d151 | aurora_BTCUSDT_1778365504313 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 352960c3-75b9-4ed7-8080-096ca3d72b58 | aurora_BTCUSDT_1778423406340 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| fc6c34fe-8e18-4a07-80b9-1594f784d93d | aurora_BTCUSDT_1778424001517 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a6910d76-9f20-4ec4-a0ca-c343c1eedd36 | aurora_BTCUSDT_1778424602438 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| b2ba9f23-ab08-4bd5-a346-373171506fde | aurora_BTCUSDT_1778429706498 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| 617b0af8-2898-4cda-9c6a-d6567c826455 | aurora_BTCUSDT_1778438706743 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| 30e065cf-a0d4-4f54-b078-c5c90ea14f41 | aurora_BTCUSDT_1778453101930 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 0bfa8d79-ebd9-4f7c-9cea-dc06773e058a | aurora_BTCUSDT_1778459104860 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 6b0a0732-94de-4594-9321-d413e88d92b1 | aurora_BTCUSDT_1778473203744 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 7c2afacf-f90b-4943-b757-0686d2447938 | aurora_BTCUSDT_1778476203284 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
| f555a1dc-5757-4402-acc1-044fe3bd932d | aurora_BTCUSDT_1778512203705 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 9f6f4395-8020-4cc6-9664-566ddb487430 | aurora_BTCUSDT_1778516106187 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| e52fb20d-82e1-4c83-8525-c620598abc66 | aurora_BTCUSDT_1778531701079 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 7d9d75bd-94a1-43fd-93bb-9d1a503857b6 | aurora_BTCUSDT_1778532302798 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b35bbc91-3395-496f-b75e-72c1c969e5d9 | aurora_BTCUSDT_1778532902800 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0bff2479-43aa-4be3-ad33-6bbac6451441 | aurora_BTCUSDT_1778533503063 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0c784fba-2e00-4992-9495-887fae65ae36 | aurora_BTCUSDT_1778534104332 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 171194f5-4f68-4ad5-b11e-7d4212db54ab | aurora_BTCUSDT_1778534404478 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| fd80f7fe-9462-4b35-981b-6407f1bc4f0a | aurora_BTCUSDT_1778535005745 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1cd2d1e7-dfd0-4592-9811-780e303bdc4d | aurora_BTCUSDT_1778535601381 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 699f2d63-81a3-4a2c-892e-1b9142a03dd4 | aurora_BTCUSDT_1778536202014 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 20bba74f-fd8d-4c37-a0d1-8d5f5502768b | aurora_BTCUSDT_1778536803162 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e390786c-a33b-49cc-8b7c-22a427d76b51 | aurora_BTCUSDT_1778537404018 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 54e2a320-0161-4f9c-b441-db9cb84aca9b | aurora_BTCUSDT_1778538004935 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6c1d916a-7974-4898-9ddb-5bc15513f32b | aurora_BTCUSDT_1778538601322 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 08cdc5ce-80cc-4865-9245-81a9baa766c4 | aurora_BTCUSDT_1778539201909 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a7b1107c-eaef-48b5-831f-87e68a5c6d7f | aurora_BTCUSDT_1778539802849 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e91c47bb-4fba-4908-9baa-6920401d2d0e | aurora_BTCUSDT_1778540404305 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 622b4914-6b02-43ce-bc17-47a174345e93 | aurora_BTCUSDT_1778541004769 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d4fb7331-134e-41ca-ab40-cdd70b483e88 | aurora_BTCUSDT_1778542503190 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b178d561-db27-426d-b1f2-751d835c4c39 | aurora_BTCUSDT_1778543104386 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 170363b4-3955-4875-89a0-4c86c1d4677b | aurora_BTCUSDT_1778543705166 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 57ef77f3-68fc-41ea-bf76-3d30c584c63c | aurora_BTCUSDT_1778544301135 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bfec64c6-1ef2-49e5-adf3-e9bf76c4e587 | aurora_BTCUSDT_1778544902611 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 58ae95e9-abd9-4187-a7d2-43f82929e7a4 | aurora_BTCUSDT_1778545503146 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2a1b532e-ee35-4694-9a64-c2dcd0f4d1b9 | aurora_BTCUSDT_1778546104184 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 00b66972-7fd7-4126-b439-8f6b1146dc1e | aurora_BTCUSDT_1778546705720 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| da6ae23b-89ec-45f1-995b-66cb153dd082 | aurora_BTCUSDT_1778547301370 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1e287033-d0bc-41d7-bbb9-6ba7509b0405 | aurora_BTCUSDT_1778547902385 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ed853997-292c-40d8-8b87-44272adc39c2 | aurora_BTCUSDT_1778548503851 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 80f914dd-9d66-40fd-b74f-8ae3e222c0b7 | aurora_BTCUSDT_1778549104471 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3c48695c-f5ca-4f7a-8ff0-cceb0e816c4d | aurora_BTCUSDT_1778549700275 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 727ae74f-b5bf-46f1-a357-14b363cf568c | aurora_BTCUSDT_1778552105915 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| c70b5334-a399-4223-ad4d-ff41f827b078 | aurora_BTCUSDT_1778570104771 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5c0220d8-4407-4b66-913f-934111ea24af | aurora_BTCUSDT_1778570705309 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0c0126b6-6dba-4176-bfae-9898a2c7a64f | aurora_BTCUSDT_1778571301126 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 35d6c1ea-48c0-4f06-b65d-dc19c22b8fa5 | aurora_BTCUSDT_1778571902745 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c546569f-e1d4-48ec-8cf4-bc6332286f68 | aurora_BTCUSDT_1778572502988 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5296b5e4-c98e-4227-890f-035b2eddc054 | aurora_BTCUSDT_1778573705308 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| b58576f8-748c-40bd-9478-221711631e18 | aurora_BTCUSDT_1778586305230 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8ec0d671-e2ad-4aca-b865-084be7c2c827 | aurora_BTCUSDT_1778586905530 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a4c33324-ffe7-42ba-b335-789d84c12c4f | aurora_BTCUSDT_1778587501365 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 825112f0-507a-4dde-9376-d388a76534d2 | aurora_BTCUSDT_1778588102906 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| be1c08c3-2955-454e-9fc7-d474fb4f968a | aurora_BTCUSDT_1778588703068 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 94d4fce8-3a5e-4057-b4ea-16d92aaa1416 | aurora_BTCUSDT_1778589304338 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| cbfd5c17-26f4-4ad0-80e8-3161499f7ef8 | aurora_BTCUSDT_1778589906260 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 971860a3-fff9-4391-804b-837a675def82 | aurora_BTCUSDT_1778590200817 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 50b58453-e3cf-461d-812e-594ac84c802d | aurora_BTCUSDT_1778592605241 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e967c0b1-271c-4da1-8426-c92aeb71aad7 | aurora_BTCUSDT_1778593200740 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 194588ad-8087-431b-8645-1ca2cb92104e | aurora_BTCUSDT_1778593801725 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5949515e-b092-473b-b58d-368fda08b95a | aurora_BTCUSDT_1778594403893 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 49593f78-b145-4bd2-85ce-08102b785fae | aurora_BTCUSDT_1778595004078 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 3356593b-1951-40f2-bf22-aedef7e80133 | aurora_BTCUSDT_1778600705231 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 9f6529fa-2083-4187-a12f-9821639e3f14 | aurora_BTCUSDT_1778612404910 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 20213d32-a061-4458-a22e-0ea4c64448b7 | aurora_BTCUSDT_1778613004676 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 0611fea8-5c94-4bab-b450-e9d13fdc768b | aurora_BTCUSDT_1778622903800 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| ed4ce599-9cbe-481f-9fcf-7b71a8999fad | aurora_BTCUSDT_1778635804134 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| dcc1aac0-f720-4f2e-b6cd-b9815feed564 | aurora_BTCUSDT_1778662804871 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 1a952a5e-6afb-46ab-bf7e-cf923f78f5d1 | aurora_BTCUSDT_1778663701052 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
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
| c4aa414a-940f-49b9-93eb-a5bac1620279 | aurora_ETHUSDT_1778428202947 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| 41711350-f9d8-47e9-8e5d-fa1405a4c97e | aurora_ETHUSDT_1778456400832 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 0a8606bb-a046-4627-aca5-dfae07a4acc8 | aurora_ETHUSDT_1778459104635 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| f3cd0ec4-a521-42e3-a640-848a432b5de2 | aurora_ETHUSDT_1778473203408 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| dd300a74-68ab-4a9e-89db-8ed39e5df9ae | aurora_ETHUSDT_1778479502991 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 240d8199-e40a-4371-88a5-f5b1404f7f90 | aurora_ETHUSDT_1778481901874 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 92f46523-526d-4e87-ae75-c2e2e113c3e0 | aurora_ETHUSDT_1778482803260 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 01099307-b9f8-4786-a136-850a7ad97fe0 | aurora_ETHUSDT_1778483403768 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 28021104-20f6-41f0-8e84-777d17058d6e | aurora_ETHUSDT_1778484901113 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d735fb63-c80d-4c94-baf3-a22c3a938925 | aurora_ETHUSDT_1778485502441 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2fdba19a-2b80-4d0e-a747-aa0c24672b69 | aurora_ETHUSDT_1778486102879 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6f907ab9-fc0d-4b56-855a-8f063501e5fd | aurora_ETHUSDT_1778486703843 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| cda22259-ca35-455e-9a1c-4cdaa584ed34 | aurora_ETHUSDT_1778487305124 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d948c01b-726e-4f03-a8e5-bac0a929f4de | aurora_ETHUSDT_1778490303428 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b90b677a-3772-4b0e-827f-1bf3b2def45e | aurora_ETHUSDT_1778490904624 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e5164015-1dd6-496f-909f-8ed2d773e352 | aurora_ETHUSDT_1778492101015 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bde430ff-36a7-4b48-9f0b-f4095a2faf51 | aurora_ETHUSDT_1778492702367 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bfa7042b-718d-47ae-ba14-9f7c023a4afa | aurora_ETHUSDT_1778493302894 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 93765924-327a-4e83-8ffa-53dd388ceda5 | aurora_ETHUSDT_1778493904017 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1a4be08f-bf03-4600-95ee-25d0bf75562a | aurora_ETHUSDT_1778494505269 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 825cdef4-08d5-4105-bdbf-cdc7db457e79 | aurora_ETHUSDT_1778494805475 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 45b93ed1-c810-48bd-802b-435aeb712a6d | aurora_ETHUSDT_1778495401614 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9b829839-8c21-41f7-a5eb-105f160768f6 | aurora_ETHUSDT_1778496603064 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1e46049c-ac94-4b63-bcba-d862f8e3f1e5 | aurora_ETHUSDT_1778499301647 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6d65633d-d23d-45de-85f6-af6756a8e31c | aurora_ETHUSDT_1778499902975 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9068a6eb-20cc-4e9e-b449-9e1d3c8d72d8 | aurora_ETHUSDT_1778500503372 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 26ad33e8-f9b3-4364-b97c-55ef1e4a215f | aurora_ETHUSDT_1778502000805 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3e75e8aa-cc98-4a33-8034-9435bce9fc20 | aurora_ETHUSDT_1778512203285 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| ebdf38bc-bbc3-45ef-aab1-dc8a79b33b56 | aurora_ETHUSDT_1778520602841 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8381ceb4-7585-44fe-9a9d-fcaf50e1b520 | aurora_ETHUSDT_1778520902840 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3c58309e-30a6-427d-b10e-a8cf7ca37344 | aurora_ETHUSDT_1778521504355 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8c812b2e-d83d-4811-992b-062442233e6c | aurora_ETHUSDT_1778522701096 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d0796fd2-9f9c-4b88-86ce-8c3218abf19e | aurora_ETHUSDT_1778523903005 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c297d4c1-eb47-45b2-81b7-bb4ddae6eac1 | aurora_ETHUSDT_1778524503918 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6416401b-1276-48d2-8777-3ab09da67ab8 | aurora_ETHUSDT_1778527202990 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b447505a-2600-4560-99e9-5ce1474b1953 | aurora_ETHUSDT_1778529902654 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 01844311-5d81-46e1-b32c-802487825cfb | aurora_ETHUSDT_1778531700585 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b74320e5-56b4-4455-bbc8-7814051ebfa6 | aurora_ETHUSDT_1778534404303 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0cc54852-0191-46b6-964f-a88b450072ff | aurora_ETHUSDT_1778535005514 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e61671b1-b369-44d8-8c8f-e7ba2150e6f9 | aurora_ETHUSDT_1778535601177 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 980e7bab-12a1-4d46-bb18-639fb02c6dd8 | aurora_ETHUSDT_1778536201884 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| cbf23990-a431-476e-84b7-69dff422acb8 | aurora_ETHUSDT_1778536802966 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d5e3e463-51cd-42a1-99b8-8b0c7a45f979 | aurora_ETHUSDT_1778537403851 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f9f3736b-0d2e-4607-b264-b8536ab8c6aa | aurora_ETHUSDT_1778538004747 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b7c6b712-b7c0-4d35-8620-ef46db2e5f5d | aurora_ETHUSDT_1778539201746 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c722d118-8bb6-4085-9e9c-565bf9aed742 | aurora_ETHUSDT_1778541305459 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 615684cc-ab5f-4b5a-85a4-6f79d9cabf2b | aurora_ETHUSDT_1778542502947 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ef52694c-2a82-4c75-8d30-dcdcb70e90e9 | aurora_ETHUSDT_1778543104061 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c1cc69ae-5394-419a-a791-b12013076c95 | aurora_ETHUSDT_1778544000754 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a8a48fc5-0329-4802-aaf7-4d19f7f1d5af | aurora_ETHUSDT_1778545202439 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 65cecb5e-8bbb-4121-aaa7-0544c60c5f3e | aurora_ETHUSDT_1778545803780 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| cf2fb925-a7ea-4517-99e3-7390e0a1142b | aurora_ETHUSDT_1778546404575 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3cacb33a-c6dd-450b-bc3a-6168067683e7 | aurora_ETHUSDT_1778547000608 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| be8dd812-296f-4af4-a8a7-9a6b574f6793 | aurora_ETHUSDT_1778547601992 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a5d18973-28f4-466b-9ad3-2b5eb8277d74 | aurora_ETHUSDT_1778548202779 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d66df2ab-6d84-4724-ab96-4bd5bc263dbd | aurora_ETHUSDT_1778548803819 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b7064e77-61fb-4802-ab4b-5cea15ce660b | aurora_ETHUSDT_1778549405081 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3f9072cc-c98c-49c6-91b3-871365f0ee5a | aurora_ETHUSDT_1778559902897 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3ec00ee9-4dec-4973-a7a2-8951856e9504 | aurora_ETHUSDT_1778560503860 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 71a55328-7d0b-4ba1-806d-4f5e112b67aa | aurora_ETHUSDT_1778561105181 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4e9edd96-6a88-448a-9732-b428e9d18bfe | aurora_ETHUSDT_1778561700716 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6e79b017-916b-4242-88f4-439ed5dd4ce9 | aurora_ETHUSDT_1778562301662 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bb70a2d6-c9ff-4b97-991b-e36f7445b636 | aurora_ETHUSDT_1778562902981 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c397ae61-91b7-43be-8b0d-016141b96aef | aurora_ETHUSDT_1778565000983 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f04c9f97-9c4b-475c-8597-9bcb0ee367aa | aurora_ETHUSDT_1778565602276 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2c9cd4f6-e461-4cb2-8cdd-d53a8a40f0ff | aurora_ETHUSDT_1778566202906 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 80d10e90-3c17-4261-8e1c-8c77437edf5f | aurora_ETHUSDT_1778567704908 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| fa61b364-72c7-4d5a-bf9d-df4b02bac28d | aurora_ETHUSDT_1778568901731 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f16547ef-7d13-4582-848e-ed9e33c088dc | aurora_ETHUSDT_1778569502790 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1135dfca-3c82-4002-9012-758871d5ecbd | aurora_ETHUSDT_1778570104259 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d1f9f247-4771-47a5-b8ce-1711166ab42a | aurora_ETHUSDT_1778570704984 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e7af7347-2739-47e5-8964-dbb6babb72b9 | aurora_ETHUSDT_1778571300863 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8c888a46-c60a-4acd-85df-b79794dc3437 | aurora_ETHUSDT_1778571902218 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| be75fb74-c0ec-4cc2-a974-5162f1926df1 | aurora_ETHUSDT_1778572502728 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 15c1b260-dc99-457e-a15e-7414e7b17e4a | aurora_ETHUSDT_1778583003998 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 118f2b06-fd74-4eb4-a3a8-419515428e4e | aurora_ETHUSDT_1778583605287 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f004e0a6-aa9a-4bd8-b715-391140389071 | aurora_ETHUSDT_1778584201153 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| be369ad5-9d6e-422c-8b74-1f8e21309570 | aurora_ETHUSDT_1778584802034 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 80d6a5a1-31f1-41ba-b98b-2bab45290661 | aurora_ETHUSDT_1778585403334 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5cfb3593-90c7-4a91-9071-36b999a7b74c | aurora_ETHUSDT_1778586003874 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 70ad437d-f33e-453b-ae45-88cb242a01ae | aurora_ETHUSDT_1778587501064 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b149aee5-2678-4fe0-a35c-b06be1635d28 | aurora_ETHUSDT_1778588102389 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 81d23f00-2385-42cd-ac4b-89683b12e54a | aurora_ETHUSDT_1778618703289 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 6fb9fe79-d2f7-4033-9951-ec59f86f7b97 | aurora_ETHUSDT_1778619303704 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| cbb19ab4-324a-4fc0-b38e-67508f339bd8 | aurora_ETHUSDT_1778619904187 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 791737f0-1803-4e5e-a4ea-ae6a447985cc | aurora_ETHUSDT_1778620500486 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e0ea9db6-261b-474c-8c62-4cfd8f67c509 | aurora_ETHUSDT_1778621100999 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9b854dd9-bb60-4090-bcef-1b09d1145975 | aurora_ETHUSDT_1778622302911 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ece55aa9-cca1-412d-84ea-1ef96cc3d237 | aurora_ETHUSDT_1778622903609 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 42859bab-aadd-4f06-a5e0-af0ab26f0cf3 | aurora_ETHUSDT_1778623504472 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| e36e57d8-f64d-4be7-8cec-14dd69ba073b | aurora_ETHUSDT_1778625903359 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c3d48f4c-b624-4a51-b9e0-0a1868877031 | aurora_ETHUSDT_1778626203489 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c888412f-230a-4f1f-a148-aed5c68ec8e0 | aurora_ETHUSDT_1778626804611 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2cc78eb0-6d27-472a-8343-f4d6d032677c | aurora_ETHUSDT_1778627400333 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b188e004-be42-4740-8206-705144ad9bcc | aurora_ETHUSDT_1778628001196 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 981e0f37-70b8-4f14-be80-80c1269bc85e | aurora_ETHUSDT_1778628602504 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 1e97e19f-2a6c-453e-af2f-01025830276e | aurora_ETHUSDT_1778629203080 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 8bc28473-3a7b-4443-8b20-71ec1e455a5c | aurora_ETHUSDT_1778629803949 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 21473170-b41e-44b3-9d8f-41816aa99f02 | aurora_ETHUSDT_1778630405260 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c8f95b11-e114-4a3a-8f60-47294f02cd45 | aurora_ETHUSDT_1778631000925 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ce2b40f8-1b0c-4637-a697-19927ffb3c08 | aurora_ETHUSDT_1778631601864 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b9b5fb5f-4adc-445e-8169-fe4015573e20 | aurora_ETHUSDT_1778662804339 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| bf444bd1-f3e5-4601-bf91-a98dde0d44ca | aurora_ETHUSDT_1778668802619 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ff3151b6-59e2-4ea3-8607-a96499d22d0b | aurora_ETHUSDT_1778669403398 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3212a019-aa83-4863-8292-c34e7f156252 | aurora_ETHUSDT_1778670004420 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bc29ea0a-be2a-4859-bc8c-3a3aa4de5d6e | aurora_XRPUSDT_1778375104123 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 962df9c0-5524-4c77-84cf-c674dd862398 | aurora_XRPUSDT_1778375705811 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3b8dc243-e2cb-4e21-8faf-cdfbe1fc1035 | aurora_XRPUSDT_1778376305663 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 35558a53-2a9c-4f48-aa0e-e346344319d3 | aurora_XRPUSDT_1778376901653 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| df877b80-3d1d-4e8a-a5de-f94dba6e6f5f | aurora_XRPUSDT_1778377502943 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4200ccbc-ad87-45d0-8549-dfa05af6023e | aurora_XRPUSDT_1778378103489 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5e1ce104-a33f-49e0-9946-420ee2c5dfb5 | aurora_XRPUSDT_1778378704419 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a82c414d-7d23-4b3c-8d94-cc1b2f6ba69c | aurora_XRPUSDT_1778379306308 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4f2bcf1c-c0d3-4af7-8a2f-1b18e8a57570 | aurora_XRPUSDT_1778379901156 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c87f2987-72ec-4376-85a2-707becdc604a | aurora_XRPUSDT_1778381403373 | SOURCE_LOGGING_GAP | close evidence exists only in supplemental order_log surfaces |
| f86d4702-0060-44fa-8b0c-f60959b90dd3 | aurora_XRPUSDT_1778382005365 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 3b08ec21-e398-4a47-bf90-bfcfc64d94af | aurora_XRPUSDT_1778402706854 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 8a0191d1-3084-4ebf-9939-dfef1e4fe9ce | aurora_XRPUSDT_1778403902494 | CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | close evidence exists only under a suffix alias rid |
| e806c966-ada3-40ce-a46f-ebb6979e28bf | aurora_XRPUSDT_1778414705236 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| e4909e56-e8f4-4291-a129-56615abec5f5 | aurora_XRPUSDT_1778425205790 | CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | close evidence exists only under a suffix alias rid |
| 844759bd-cafb-4842-a8e4-0645d416359c | aurora_XRPUSDT_1778430903673 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| b3c22bf3-a7d7-4996-9471-ac0f4ac1dbf6 | aurora_XRPUSDT_1778439003565 | LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | order evidence is present only through lifecycle bridge keys |
| dfe3dd1d-321e-40eb-b0f2-717c47f212b1 | aurora_XRPUSDT_1778440204644 | CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED | close evidence exists only under a suffix alias rid |
| a4110d8a-4cc0-44c0-a897-477b41ea99b8 | aurora_XRPUSDT_1778448901024 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 096e91be-8eb1-40d9-a6bc-a216b0971917 | aurora_XRPUSDT_1778449201277 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 04163a13-07d4-42fb-930f-7b8d87d82cf0 | aurora_XRPUSDT_1778449502540 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| a17bf4c7-75dd-4457-bb17-1ce91ca7cb53 | aurora_XRPUSDT_1778450404390 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 9de2ae4c-e000-47b9-ad6c-df61a700a47f | aurora_XRPUSDT_1778450704254 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 685039c1-1dd9-45ec-8285-b10c0476f9df | aurora_XRPUSDT_1778452801472 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 190215a4-17cc-4426-a1fe-098d05a6dec0 | aurora_XRPUSDT_1778471106715 | REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY | decision ledger has realized fields but no order_log / trade_lifecycle close proof was found |
| 46f6e448-560a-44f2-a34c-7c794427e18b | aurora_XRPUSDT_1778473806073 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f503b9fc-4488-4f00-952c-1b742ec8541a | aurora_XRPUSDT_1778474405965 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 4c87a3f5-7ae2-4a52-ac42-b4e5eb9acd37 | aurora_XRPUSDT_1778477406843 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 80ce9893-5c44-4a34-9058-87c81f1ea3db | aurora_XRPUSDT_1778478001241 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 76299088-3fe6-4802-8f71-8a46fe2be96c | aurora_XRPUSDT_1778482804669 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 930294a0-b333-430e-b83c-1f78800357e0 | aurora_XRPUSDT_1778490304102 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| a177502e-8456-424b-98e1-6d5a1b93643b | aurora_XRPUSDT_1778490905861 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ea81a063-e9eb-4a4a-a029-ca1447712c56 | aurora_XRPUSDT_1778497804458 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c88ea500-506b-40fa-9dbf-84f8d29790c8 | aurora_XRPUSDT_1778501105381 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 58f4c212-dcf0-410b-8f00-8a7eb5a347b0 | aurora_XRPUSDT_1778501707595 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2bf4bb6b-15b6-4f0d-b017-6a08d7bdadda | aurora_XRPUSDT_1778502302019 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 86dbf2f9-6475-4ac1-a66b-732a9693317d | aurora_XRPUSDT_1778512506317 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| d485c1b3-7717-4b1c-a0c1-8c146a4b361f | aurora_XRPUSDT_1778513105442 | CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED |
| 4d177d2a-7689-4f70-ab63-de4421b35a75 | aurora_XRPUSDT_1778523903958 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 7f296b1d-5119-4d85-9d6b-732a1c6ab7d3 | aurora_XRPUSDT_1778526302761 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 3577a0cc-0fb2-4794-9311-a0be2ac00d2a | aurora_XRPUSDT_1778526904878 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 991ab40c-d6c2-47d7-a02c-4315b2a07ee0 | aurora_XRPUSDT_1778527504581 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 67e17596-7a17-40d3-ab9a-c4a9b73e5ee1 | aurora_XRPUSDT_1778528703175 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 09cef876-e494-41d2-bb49-b6ba7462f71b | aurora_XRPUSDT_1778535301104 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| acfe7197-4f25-4a66-9f8e-c03ed4e1b351 | aurora_XRPUSDT_1778537103680 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| aa130b76-925a-4190-9090-b9fbee7f7bb3 | aurora_XRPUSDT_1778537705332 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 825f6d92-182a-4dc3-a62e-c9c32a9c9476 | aurora_XRPUSDT_1778556903530 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 2b698f0c-1aff-4d7f-a9a3-17a437c0ef79 | aurora_XRPUSDT_1778557505578 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| d6a7b041-f020-4898-9772-13ba1e61819e | aurora_XRPUSDT_1778558105674 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b7bec087-2797-427c-a090-820f116b67b3 | aurora_XRPUSDT_1778558701597 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ac140f01-f458-4c6e-b40b-7b458edb3e65 | aurora_XRPUSDT_1778560804791 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5f522310-8ac0-41d0-b066-361538bb6a94 | aurora_XRPUSDT_1778561405776 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 0903728f-fed9-4d6a-ad90-9a5b0253f283 | aurora_XRPUSDT_1778562002778 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| bd9eacbc-8ee2-44f6-97f1-bab3519a0471 | aurora_XRPUSDT_1778562602719 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 5b966eed-7b58-4c00-a200-15c49430dbaf | aurora_XRPUSDT_1778575504391 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| 581ea29f-0040-4874-bc3a-05eb48d521c5 | aurora_XRPUSDT_1778612704629 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| b78ce159-9cfe-427d-a9d0-36c7d359b2c5 | aurora_XRPUSDT_1778615704482 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| dd17d4ce-54be-469d-bc08-b12bf2cb58f2 | aurora_XRPUSDT_1778616305004 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 647a04c2-3586-48d4-a4c7-d9097bccd3e1 | aurora_XRPUSDT_1778617501752 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 34ce1ad3-cb71-406a-b4ca-2f5ed974fabb | aurora_XRPUSDT_1778619304519 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 014e84ad-3e91-4f93-ba99-a5224df83ef8 | aurora_XRPUSDT_1778619904525 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 27b6b51b-d8ef-4149-83b4-99f98e614e0a | aurora_XRPUSDT_1778664902553 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| f4460b22-76f3-4dc6-bea8-6b26c521f4ce | aurora_XRPUSDT_1778665504118 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| da3c79fa-18d7-40b3-bb4e-53edf78b5b40 | aurora_XRPUSDT_1778671203079 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| c2c2566e-1b7a-45ca-9c12-5e24edddc5ef | aurora_XRPUSDT_1778671806312 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| ab3a15b0-78ab-4415-bc67-3dbe7b53f198 | aurora_XRPUSDT_1778672405282 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 912c4954-756d-44b6-ad3b-7fc1868b0cec | aurora_XRPUSDT_1778673001586 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 99ad90ce-9206-4736-8cf0-c123b61907f1 | aurora_XRPUSDT_1778674202508 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 48b787f5-a230-475e-8b47-5627fa8182fc | aurora_XRPUSDT_1778674803181 | NOT_EXECUTED_OR_REJECTED | terminal status or runtime terminal evidence indicates rejection / non-execution |
| 85bca62d-876b-4f38-b287-b116c0f1c44e | aurora_XRPUSDT_1778679600656 | CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | authority order_log contains POSITION_CLOSED but the row still remained unmatched |
| b6acf83d-533c-4607-87fb-9cf01c59ce83 | mdamr-46e01379f472b1c7 | INCONCLUSIVE | no decisive order_log or trade_lifecycle evidence was available for the unmatched decision |
