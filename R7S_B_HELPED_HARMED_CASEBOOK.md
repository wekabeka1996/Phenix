# R7S-B Helped/Harmed Casebook

## Scope

These are lifecycle-level proxy cases grouped across duplicate candidate rows. A case appears once per lifecycle/trigger timestamp, with the candidate set that shared that same first-trigger moment.

Important: helped/harmed here are proxy labels, not filled exit confirmations. In every helped case below, trigger_net_proxy remained negative; the candidate only looked better than the eventual realized loss, not profitable in absolute net terms.

## Helped Proxy Cases

| Lifecycle | Symbol | Candidates | Trigger UTC | Peak Edge USD | Trigger Net Proxy | Actual Net PnL | Delta vs Actual | Close Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_XRPUSDT_1778548203246 | XRPUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T01:20:04.340000Z | 4.97 | -6.61641 | -27.86089 | 21.24448 | SL |
| aurora_BTCUSDT_1778663701052 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-13T10:10:00.145000Z | 5.64 | -7.315949 | -28.527549 | 21.2116 | CLOSE |
| aurora_ETHUSDT_1778662804339 | ETHUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-13T10:15:00.793000Z | 18.19 | -7.141621 | -22.761971 | 15.62035 | CLOSE |
| aurora_BNBUSDT_1778620205221 | BNBUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T21:50:03.672000Z | 11.56 | -8.057169 | -15.144369 | 7.0872 | CLOSE |
| aurora_BTCUSDT_1778600705231 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T17:30:05.621000Z | 18.5 | -2.751702 | -7.947702 | 5.196 | CLOSE |
| aurora_BNBUSDT_1778682001038 | BNBUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07 | 2026-05-13T14:25:01.256000Z | 0 | -14.527948 | -16.318248 | 1.7903 | CLOSE |

## Harmed Proxy Cases

| Lifecycle | Symbol | Candidates | Trigger UTC | Peak Edge USD | Trigger Net Proxy | Actual Net PnL | Delta vs Actual | Close Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_BNBUSDT_1778518204673 | BNBUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-11T16:55:05.473000Z | 0 | -7.243031 | 48.932569 | -56.1756 | TP |
| aurora_BTCUSDT_1778676306439 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-13T12:50:01.303000Z | 13.02 | -4.359728 | 45.850792 | -50.21052 | TP |
| aurora_XRPUSDT_1778577601352 | XRPUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T09:25:01.908000Z | 4.97 | -3.021527 | 23.942943 | -26.96447 | TP |
| aurora_BTCUSDT_1778516106187 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-11T16:45:07.869000Z | 24.5 | -3.918875 | 20.448626 | -24.3675 | CLOSE |
| aurora_ETHUSDT_1778551804640 | ETHUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T03:10:00.553000Z | 14.22 | -3.471967 | 12.119093 | -15.59106 | TP |
| aurora_BTCUSDT_1778573705308 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T08:20:00.114000Z | 12.6 | -6.115144 | 7.535056 | -13.6502 | CLOSE |
| aurora_BTCUSDT_1778552701340 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T02:55:04.300000Z | 3.88 | -3.242402 | 10.340398 | -13.5828 | TP |
| aurora_BNBUSDT_1778562904748 | BNBUSDT | raw_pct_0_02, raw_pct_0_05, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T05:40:05.659000Z | 1.83 | -4.249896 | 6.671204 | -10.9211 | TP |
| aurora_BTCUSDT_1778623504656 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T22:15:00.948000Z | 18.5 | -2.635129 | 7.528271 | -10.1634 | TP |
| aurora_BNBUSDT_1778562904748 | BNBUSDT | raw_pct_0_07 | 2026-05-12T06:05:09.459000Z | 3.89 | -1.999896 | 6.671204 | -8.6711 | TP |
| aurora_XRPUSDT_1778575504391 | XRPUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T08:55:04.280000Z | 4.97 | -6.420178 | -0.800458 | -5.61972 | CLOSE |
| aurora_BTCUSDT_1778595004078 | BTCUSDT | raw_pct_0_02, raw_pct_0_05, raw_pct_0_07, fee_x1_0, fee_x1_5, fee_x2_0 | 2026-05-12T14:15:05.428000Z | 0 | -3.180226 | -0.788826 | -2.3914 | CLOSE |

## Notes

- Most harmed cases were eventual TP or positive CLOSE outcomes where all six candidates would have fired earlier on a negative trigger-net proxy.
- The one visible raw-only divergence was aurora_BNBUSDT_1778562904748, where raw_pct_0_07 fired later than the other five candidates and still remained harmed.
- The strongest helped proxy was aurora_XRPUSDT_1778548203246, but even there the trigger_net_proxy was -6.6164 rather than a positive net lock-in.
