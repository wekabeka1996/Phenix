# Authority Inventory

## FACTS

| Surface | Owner/source | Units | Runtime role | Duplication risk |
|---|---|---|---|---|
| V2 sizing | `PositionQueries.calculate_position_size` | equity USDT, qty base, notional USDT | Canonical derived quantity | Low after explicit fee config |
| Margin helper | `compute_notional_target` | fraction, margin USDT, notional USDT | Pure active sizing math | No second writer |
| Instrument truth | `config/aurora/instruments.yaml` + Pydantic | base qty, quote notional | Step/min/leverage/fee SSOT | Exchange cache remains validation input |
| Proof target/cap | `p46_1g_testnet_proof.yaml` | USDT | Proof-only bound | Not a production default |
| Exposure approval | `ExposureGuard`/`SoftClipEngine` | signed/absolute USDT, margin USDT | Sole runtime exposure gate | No second guard added |
| Snapshot freshness | V2 authority policy | seconds | Fail-closed sizing truth | Previously absent |
| Adapter/FSM | one `ExecPosFSM` + `BinanceAdapter` | normalized venue payload | Sole lifecycle authority | No bypass used |

## INFERENCES

- The patch connects existing authorities rather than introducing a sizing or risk competitor.

## ASSUMPTIONS

- The command registry remains the canonical schema registry.

## UNKNOWNS

- Multiprocess snapshot publication freshness is outside this proof.
