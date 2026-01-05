
import os

F_PATH = "apps/reference/domains/decision_making/decision_making.py"

INSERTION_BLOCK = """            )

            # FTR-07: Add DecisionContext summary to psi_vector for XAI
            psi_vector = {
                "phi_OBI": float(obi_phi),
                "phi_TFI": float(tfi_phi),
                "phi_DeltaP": float(dp_phi),
                "phi_EMA_Bias": float(ema_bias_phi),
                "phi_Volume_Spike": float(volume_spike_phi),
                "phi_Volatility_State": float(volatility_state_phi),
                "phi_Depth_Imbalance": float(depth_imbalance_phi),
                "phi_Macro_Sync": float(macro_sync_phi),
                "weights": {k: float(v) for k, v in signal_weights.items()},
                # FTR-07: Semantic signals from DecisionContext
                "ctx_trend_bullish": ctx.trend.is_bullish,
                "ctx_trend_bearish": ctx.trend.is_bearish,
                "ctx_flow_buy_pressure": ctx.flow.is_buy_pressure,
                "ctx_flow_sell_pressure": ctx.flow.is_sell_pressure,
                "ctx_high_volatility": ctx.volatility.is_high_volatility,
                "ctx_illiquid": ctx.liquidity.is_illiquid,
                "ctx_crowded_long": ctx.crowding.is_crowded_long,
                "ctx_crowded_short": ctx.crowding.is_crowded_short,
            }
        else:
            def _to_dec(val: Any) -> decimal.Decimal:
                try:
                    return decimal.Decimal(str(val))
                except Exception:
                    return decimal.Decimal("0")

            # NOTE: FeatureEngineering emits delta_price as absolute price delta (USD),
            # which makes the signal scale asset-price dependent (BTC >> alts).
            # Normalize to signed, clamped pct-of-price in [-1, 1] for stability.
            price_dec = ctx.price
            dp_raw = ctx.trend.delta_price
            dp_cap_pct = decimal.Decimal("0.02")  # 2% cap (aligns with normalize_signals path)
            if price_dec > 0 and dp_cap_pct > 0:
                dp_pct = dp_raw / price_dec
                if dp_pct > dp_cap_pct:
                    dp_pct = dp_cap_pct
                elif dp_pct < -dp_cap_pct:
                    dp_pct = -dp_cap_pct
                dp_norm = dp_pct / dp_cap_pct  # [-1, 1]
            else:
                dp_pct = decimal.Decimal("0")
                dp_norm = decimal.Decimal("0")

            psi_vector = {
                "delta_price_raw": float(dp_raw),
                "delta_price_pct": float(dp_pct),
                "delta_price_norm": float(dp_norm),
            }

            # NET-ZERO SCORING IMPLEMENTATION (Incident Review 2026-01-04)
            # Fix: "Neutral Offset Bias" where baseline score (0.6) > threshold (0.1).
            # Action: Subtract neutral baselines, treat liquidity as a GATE.
            NEUTRAL_OFFSETS = {
                "ema_bias": decimal.Decimal("0.5"),
                "volume_spike": decimal.Decimal("0.0"),  # Spike is activity
                "macro_sync": decimal.Decimal("0.5"),
                "liquidity_kappa": decimal.Decimal("0.0"), # Special case: Gated
                "obi": decimal.Decimal("0.0"),           # Already centered
                "tfi": decimal.Decimal("0.0"),
                "volatility_state": decimal.Decimal("0.0"),
                "depth_imbalance": decimal.Decimal("0.5"),
                "delta_price": decimal.Decimal("0.0"),
            }

            signal_score = decimal.Decimal("0")
            for f, w in signal_weights.items():
                weight = decimal.Decimal(str(w))
                
                # Fetch Value
                if f == "delta_price":
                    val = dp_norm
                else:
                    val = _to_dec(features_data.get(f, 0.0))

                # GATE: Liquidity Kappa (Do not add to score)
                if f == "liquidity_kappa":
                    if val < decimal.Decimal("0.5"): # Hard limit gate
                        self.logger.info(f"[{symbol}] BLOCKED by Low Liquidity Gate: {val:.4f} < 0.5")
                        self._record_blocked_intent(symbol) # Track block
                        return 
                    continue # Skip adding to score

                # Normalize (Net-Zero)
                offset = NEUTRAL_OFFSETS.get(f, decimal.Decimal("0.0"))
                normalized_val = val - offset
                
                signal_score += normalized_val * weight

        # Trigger fix: added implicitly by repair loop next line connection
"""

def repair():
    with open(F_PATH, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    found_marker = False
    inserted = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        if "for f, w in signal_weights.items()" in line:
            found_marker = True
            # The next line should be '            )'
            # But currently it might be missing or empty due to bad patch
            continue

        if found_marker and not inserted:
            # We are right after the loop definition. 
            # Check if the next line is the closing paranthesis.
            # If not, we found our broken spot.
            if line.strip() != ")":
                # We are likely in the broken gap.
                # Remove the last appended line (which is the current line we just iterated to)
                # because we want to inject BEFORE it? 
                # Wait, if line is empty, we keep it? No.
                
                # Logic:
                # 1. We kept the loop line.
                # 2. We are now at line `i`. 
                # 3. If line `i` is NOT `)`, we assume `)` is missing.
                # However, if the file is just missing lines, we should just insert.
                
                # Let's verify context:
                # 2447:                 for f, w in signal_weights.items()
                # 2448: 
                # 2449:         # Regime-based...
                
                # So we are at 2448 (empty).
                # New content starts with `            )\n`.
                
                # So we just insert INSERTION_BLOCK here.
                # And we assume the current line (empty) is trash or we keep it?
                # Let's insert BEFORE the current line if we detected the gap.
                
                # Pop the current line we just added to new_lines
                new_lines.pop() 
                
                # Insert our block
                new_lines.append(INSERTION_BLOCK)
                
                # Add the current line back
                new_lines.append(line)
                
                inserted = True
                found_marker = False # Reset

    with open(F_PATH, 'w') as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    repair()
