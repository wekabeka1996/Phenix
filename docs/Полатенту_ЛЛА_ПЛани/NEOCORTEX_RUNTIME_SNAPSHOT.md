# Neocortex Runtime Report

- Generated: `2026-02-17 02:39:34 UTC`
- Status: `DEGRADED_INGESTION_ONLY`

## Key Signals
- Log path: `C:\Users\user\Music\Phenix\data\neocortex.log` (lines: 324)
- Errors: 1
- Warnings: 3
- Torch import error seen: true
- Bridge degraded alert seen: true
- Metrics rows (excluding header): 0
- Shadow intents file exists: false (bytes=0)
- Estimated feature ingest rate (tail window): 1439.22 events/sec
- Top bracketed codes: BRAIN_BRIDGE_UNAVAILABLE=1

## Recent Log Tail
```text
2026-02-17 04:38:39,297 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #203000: ETHUSDT ts=1771295919
2026-02-17 04:38:39,694 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #204000: ETHUSDT ts=1771295920
2026-02-17 04:38:40,111 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #205000: ETHUSDT ts=1771295920
2026-02-17 04:38:40,544 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #206000: ETHUSDT ts=1771295921
2026-02-17 04:38:40,942 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #207000: ETHUSDT ts=1771295921
2026-02-17 04:38:41,360 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #208000: ETHUSDT ts=1771295921
2026-02-17 04:38:41,923 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #209000: ETHUSDT ts=1771295922
2026-02-17 04:38:42,553 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #210000: ETHUSDT ts=1771295923
2026-02-17 04:38:43,081 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #211000: ETHUSDT ts=1771295923
2026-02-17 04:38:43,543 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #212000: ETHUSDT ts=1771295924
2026-02-17 04:38:43,981 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #213000: ETHUSDT ts=1771295924
2026-02-17 04:38:44,397 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #214000: ETHUSDT ts=1771295924
2026-02-17 04:38:44,816 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #215000: ETHUSDT ts=1771295925
2026-02-17 04:38:45,229 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #216000: ETHUSDT ts=1771295925
2026-02-17 04:38:45,626 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #217000: ETHUSDT ts=1771295926
2026-02-17 04:38:46,066 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #218000: ETHUSDT ts=1771295926
2026-02-17 04:38:46,479 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #219000: ETHUSDT ts=1771295926
2026-02-17 04:38:46,889 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #220000: ETHUSDT ts=1771295927
2026-02-17 04:38:47,313 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #221000: ETHUSDT ts=1771295927
2026-02-17 04:38:47,730 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #222000: ETHUSDT ts=1771295928
2026-02-17 04:38:48,107 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #223000: ETHUSDT ts=1771295928
2026-02-17 04:38:48,522 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #224000: ETHUSDT ts=1771295929
2026-02-17 04:38:48,924 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #225000: ETHUSDT ts=1771295929
2026-02-17 04:38:49,315 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #226000: ETHUSDT ts=1771295929
2026-02-17 04:38:49,687 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #227000: ETHUSDT ts=1771295930
2026-02-17 04:38:50,078 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #228000: ETHUSDT ts=1771295930
2026-02-17 04:38:50,480 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #229000: ETHUSDT ts=1771295930
2026-02-17 04:38:50,897 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #230000: ETHUSDT ts=1771295931
2026-02-17 04:38:51,316 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #231000: ETHUSDT ts=1771295931
2026-02-17 04:38:51,728 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #232000: ETHUSDT ts=1771295932
2026-02-17 04:38:52,142 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #233000: ETHUSDT ts=1771295932
2026-02-17 04:38:52,598 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #234000: ETHUSDT ts=1771295933
2026-02-17 04:38:53,092 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #235000: ETHUSDT ts=1771295933
2026-02-17 04:38:53,552 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #236000: ETHUSDT ts=1771295934
2026-02-17 04:38:53,978 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #237000: ETHUSDT ts=1771295934
2026-02-17 04:38:54,394 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #238000: ETHUSDT ts=1771295934
2026-02-17 04:38:54,808 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #239000: ETHUSDT ts=1771295935
2026-02-17 04:38:55,521 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #240000: ETHUSDT ts=1771295936
2026-02-17 04:38:56,291 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #241000: ETHUSDT ts=1771295936
2026-02-17 04:38:57,120 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #242000: ETHUSDT ts=1771295937
2026-02-17 04:38:58,089 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #243000: ETHUSDT ts=1771295938
2026-02-17 04:38:58,936 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #244000: ETHUSDT ts=1771295939
2026-02-17 04:38:59,829 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #245000: ETHUSDT ts=1771295940
2026-02-17 04:39:00,657 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #246000: ETHUSDT ts=1771295941
2026-02-17 04:39:01,482 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #247000: ETHUSDT ts=1771295941
2026-02-17 04:39:02,340 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #248000: ETHUSDT ts=1771295942
2026-02-17 04:39:03,198 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #249000: ETHUSDT ts=1771295943
2026-02-17 04:39:04,134 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #250000: ETHUSDT ts=1771295944
2026-02-17 04:39:04,943 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #251000: ETHUSDT ts=1771295945
2026-02-17 04:39:05,969 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #252000: ETHUSDT ts=1771295946
2026-02-17 04:39:06,969 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #253000: ETHUSDT ts=1771295947
2026-02-17 04:39:07,998 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #254000: ETHUSDT ts=1771295948
2026-02-17 04:39:08,912 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #255000: ETHUSDT ts=1771295949
2026-02-17 04:39:09,931 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #256000: ETHUSDT ts=1771295950
2026-02-17 04:39:10,885 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #257000: ETHUSDT ts=1771295951
2026-02-17 04:39:11,845 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #258000: ETHUSDT ts=1771295952
2026-02-17 04:39:12,814 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #259000: ETHUSDT ts=1771295953
2026-02-17 04:39:13,832 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #260000: ETHUSDT ts=1771295954
2026-02-17 04:39:14,741 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #261000: ETHUSDT ts=1771295955
2026-02-17 04:39:15,750 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #262000: ETHUSDT ts=1771295956
2026-02-17 04:39:16,796 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #263000: ETHUSDT ts=1771295957
2026-02-17 04:39:17,762 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #264000: ETHUSDT ts=1771295958
2026-02-17 04:39:18,746 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #265000: ETHUSDT ts=1771295959
2026-02-17 04:39:19,746 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #266000: ETHUSDT ts=1771295960
2026-02-17 04:39:20,724 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #267000: ETHUSDT ts=1771295961
2026-02-17 04:39:21,646 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #268000: ETHUSDT ts=1771295962
2026-02-17 04:39:22,652 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #269000: ETHUSDT ts=1771295963
2026-02-17 04:39:23,650 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #270000: ETHUSDT ts=1771295964
2026-02-17 04:39:24,557 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #271000: ETHUSDT ts=1771295965
2026-02-17 04:39:25,431 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #272000: SOLUSDT ts=1771295965
2026-02-17 04:39:26,227 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #273000: SOLUSDT ts=1771295966
2026-02-17 04:39:27,106 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #274000: SOLUSDT ts=1771295967
2026-02-17 04:39:28,041 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #275000: SOLUSDT ts=1771295968
2026-02-17 04:39:28,930 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #276000: SOLUSDT ts=1771295969
2026-02-17 04:39:29,879 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #277000: SOLUSDT ts=1771295970
2026-02-17 04:39:30,828 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #278000: SOLUSDT ts=1771295971
2026-02-17 04:39:31,585 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #279000: SOLUSDT ts=1771295972
2026-02-17 04:39:32,527 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #280000: SOLUSDT ts=1771295973
2026-02-17 04:39:33,458 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #281000: SOLUSDT ts=1771295973
2026-02-17 04:39:34,188 | INFO     | apps.reference.domains.neocortex.logic.ingest.multi_tailer | Feature #282000: SOLUSDT ts=1771295974
```

## Interpretation
- System is running in degraded mode: ingestion active, training disabled.
- This is expected fail-safe when BrainBridge cannot initialize.
- Main blocker to full R2 behavior is missing PyTorch runtime in current environment.
- Telemetry CSV has no data rows yet; either no training/intent flow, or logging path issue.
- No shadow intent JSONL produced yet.
