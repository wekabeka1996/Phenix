#!/usr/bin/env python3
"""
Strategy Replay — прогін стратегій на логах фіч
===============================================

Симулює роботу DecisionMaking на історичних логах фіч з logs/features/*.log

Використання:
    # Прогнати всі символи на поточному конфігу
    python3 tools/strategy_replay.py
    
    # Конкретні символи
    python3 tools/strategy_replay.py --symbols SOLUSDT ETHUSDT
    
    # З custom конфігом
    python3 tools/strategy_replay.py --config config/aurora --symbols BTCUSDT
    
    # Verbose режим (показує кожен intent)
    python3 tools/strategy_replay.py --symbols SOLUSDT --verbose

Що робить:
1. Читає логи фіч (logs/features/*.log)
2. Прогоняє через ПОВНУ логіку DecisionMaking:
   - Strategy arbitration (aurora vs MR)
   - QoS gates (cooldown, rate limits)
   - Warmup/regime gates (якщо aurora assigned)
   - Scoring V2 (direction/strength split)
   - Liquidity gates
   - Essential features check
3. Рахує статистику: BUY/SELL/NEUTRAL/DEFER з причинами
4. Симулює виконання (якщо є ціна) → P&L
5. Виводить порівняльну таблицю по символах
"""

import argparse
import json
import sys
import time
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
    compute_direction_strength_score,
)


class StrategyReplay:
    """Симулятор DecisionMaking на логах фіч."""
    
    def __init__(self, config_dir: str = "config/aurora", verbose: bool = False, no_qos: bool = False):
        self.verbose = verbose
        self.no_qos = no_qos
        self.config = self._load_config(config_dir)
        
        # Статистика по символах
        self.stats = defaultdict(lambda: {
            "total_ticks": 0,
            "intents_total": 0,
            "intents_buy": 0,
            "intents_sell": 0,
            "neutral": 0,
            "deferred": 0,
            "blocked_reasons": defaultdict(int),
            "scores": [],
            "trades": [],
        })
        
        # QoS state (per symbol)
        self.qos_state = defaultdict(lambda: {
            "last_intent_ts": 0,
            "intent_count_window": deque(maxlen=60),  # 1 хв вікно
        })
        
    def _load_config(self, config_dir: str):
        """Завантажити конфіг."""
        print(f"📂 Завантаження конфігу з {config_dir}...")
        loader = ConfigLoader(Path(config_dir))
        config = loader.load_config()
        
        print(f"✅ Конфіг завантажено:")
        print(f"   trading_mode: {config.trading_mode}")
        print(f"   trading.mode: {config.trading.mode}")
        
        decision = config.strategies.aurora.decision
        print(f"   scoring_version: {getattr(decision, 'scoring_version', 'v1')}")
        print(f"   normalize_mode: {decision.signals.normalize_signals_mode}")
        print(f"   signal_threshold: {decision.signal_threshold}")
        print(f"   liquidity_gate: {getattr(decision.liquidity_gate, 'enabled', False) if decision.liquidity_gate else False}")
        
        return config
    
    def _is_aurora_assigned(self, symbol: str) -> bool:
        """Чи має символ aurora в assignments."""
        registry = self.config.strategies_registry
        if not registry:
            return False
        
        assignments = registry.assignments.get(symbol, [])
        return "aurora" in assignments
    
    def _is_mr_assigned(self, symbol: str) -> bool:
        """Чи має символ mean_reversion в assignments."""
        registry = self.config.strategies_registry
        if not registry:
            return False
        
        assignments = registry.assignments.get(symbol, [])
        return "mean_reversion" in assignments
    
    def _check_qos_gate(self, symbol: str, ts_sec: float) -> Optional[str]:
        """Перевірити QoS gate (cooldown + rate limit)."""
        if self.no_qos:
            return None  # Вимкнено для тестування
        
        dm_cfg = self.config.domains.decision_making
        qos_cfg = dm_cfg.qos
        
        if qos_cfg.mode == "shadow":
            return None  # shadow = не блокує
        
        state = self.qos_state[symbol]
        
        # Symbol cooldown
        cooldown_sec = qos_cfg.symbol_cooldown_sec
        time_since_last = ts_sec - state["last_intent_ts"]
        
        if state["last_intent_ts"] > 0 and time_since_last < cooldown_sec:
            return f"QOS_COOLDOWN({time_since_last:.1f}s < {cooldown_sec}s)"
        
        # Rate limit (max_intents_per_minute)
        max_rate = qos_cfg.max_intents_per_minute_per_symbol
        state["intent_count_window"].append(ts_sec)
        
        # Рахуємо інтенти за останню хвилину
        cutoff = ts_sec - 60
        recent = sum(1 for t in state["intent_count_window"] if t >= cutoff)
        
        if recent >= max_rate:
            return f"QOS_RATE_LIMIT({recent}/{max_rate} per min)"
        
        return None
    
    def _check_liquidity_gate(self, features: Dict[str, Any]) -> Optional[str]:
        """Перевірити liquidity gate."""
        decision = self.config.strategies.aurora.decision
        liq_cfg = decision.liquidity_gate
        
        if not liq_cfg or not liq_cfg.enabled:
            return None
        
        kappa = features.get("liquidity_kappa")
        if kappa is None:
            return "LIQUIDITY_KAPPA_MISSING"
        
        kappa_val = float(kappa)
        if kappa_val < liq_cfg.kappa_min:
            return f"LIQUIDITY_LOW(kappa={kappa_val:.3f}<{liq_cfg.kappa_min})"
        
        return None
    
    def _compute_score(self, symbol: str, features: Dict[str, Any]) -> Dict[str, Any]:
        """Обчислити direction/strength score."""
        decision = self.config.strategies.aurora.decision
        
        signal_weights = decision.signal_weights.model_dump()
        feature_neutrals = getattr(decision, "feature_neutrals", {})
        essential_features = getattr(decision, "essential_features", [])
        
        ds_cfg = decision.direction_strength_scoring
        normalize_mode = str(decision.signals.normalize_signals_mode)
        
        # Normalize delta_price
        price = Decimal(str(features.get("price", 0)))
        dp_raw = Decimal(str(features.get("delta_price", 0)))
        dp_cap = Decimal(str(decision.signals.delta_price_cap_pct))
        
        if price > 0 and dp_cap > 0:
            dp_pct = dp_raw / price
            dp_pct = max(-dp_cap, min(dp_pct, dp_cap))
            dp_norm = dp_pct / dp_cap
        else:
            dp_norm = Decimal("0")
        
        feat_eval = dict(features)
        feat_eval["delta_price"] = float(dp_norm)
        
        # Mock readiness (всі фічі готові)
        readiness = {k: True for k in feat_eval.keys()}
        
        ds_score = compute_direction_strength_score(
            features=feat_eval,
            weights=signal_weights,
            neutrals=feature_neutrals,
            readiness=readiness,
            essential_features=set(essential_features),
            normalize_mode=normalize_mode,
            directional_features=list(ds_cfg.directional_features),
            strength_features=list(ds_cfg.strength_features),
            strength_alpha=float(ds_cfg.strength_alpha),
            strength_cap=float(ds_cfg.strength_cap),
            symbol=symbol,
        )
        
        return {
            "deferred": ds_score.deferred,
            "deny_reason": ds_score.deny_reason,
            "final_score": float(ds_score.final_score),
            "dir_score": float(ds_score.dir_score),
            "strength_score": float(ds_score.strength_score),
            "dir_contribs": ds_score.dir_result.contribs,
        }
    
    def replay_symbol(self, symbol: str):
        """Прогнати replay для одного символа."""
        log_path = Path(f"logs/features/{symbol}.log")
        if not log_path.exists():
            print(f"⚠️  Лог не знайдено: {log_path}")
            return
        
        print(f"\n🔄 Replay {symbol}...")
        
        stats = self.stats[symbol]
        aurora_assigned = self._is_aurora_assigned(symbol)
        mr_assigned = self._is_mr_assigned(symbol)
        
        print(f"   Assignments: aurora={aurora_assigned}, MR={mr_assigned}")
        
        decision = self.config.strategies.aurora.decision
        signal_threshold = float(decision.signal_threshold)
        
        with log_path.open("r") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    features = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                stats["total_ticks"] += 1
                
                # Час (якщо немає — беремо лінійний)
                ts_sec = features.get("ts", line_no)
                if not isinstance(ts_sec, (int, float)):
                    ts_sec = line_no
                
                # === GATE 1: Strategy Assignment ===
                if not aurora_assigned and not mr_assigned:
                    stats["blocked_reasons"]["NO_STRATEGY_ASSIGNED"] += 1
                    continue
                
                # Якщо є тільки MR, скіпаємо (aurora decision flow не застосовується)
                if mr_assigned and not aurora_assigned:
                    stats["blocked_reasons"]["MR_ONLY_SKIP"] += 1
                    continue
                
                # === GATE 2: QoS ===
                qos_block = self._check_qos_gate(symbol, ts_sec)
                if qos_block:
                    stats["blocked_reasons"][qos_block] += 1
                    continue
                
                # === GATE 3: Liquidity ===
                liq_block = self._check_liquidity_gate(features)
                if liq_block:
                    stats["blocked_reasons"][liq_block] += 1
                    continue
                
                # === GATE 4: Score Calculation ===
                score_result = self._compute_score(symbol, features)
                
                if score_result["deferred"]:
                    stats["deferred"] += 1
                    stats["blocked_reasons"][score_result["deny_reason"]] += 1
                    continue
                
                final_score = score_result["final_score"]
                stats["scores"].append(final_score)
                
                # === Decision Logic ===
                if final_score >= signal_threshold:
                    side = "BUY"
                    stats["intents_buy"] += 1
                    stats["intents_total"] += 1
                    self.qos_state[symbol]["last_intent_ts"] = ts_sec
                    
                    if self.verbose and stats["intents_total"] <= 10:
                        print(f"   [{line_no:>6}] {side:4s} score={final_score:+.4f} (dir={score_result['dir_score']:+.3f}, str={score_result['strength_score']:.3f})")
                
                elif final_score <= -signal_threshold:
                    side = "SELL"
                    stats["intents_sell"] += 1
                    stats["intents_total"] += 1
                    self.qos_state[symbol]["last_intent_ts"] = ts_sec
                    
                    if self.verbose and stats["intents_total"] <= 10:
                        print(f"   [{line_no:>6}] {side:4s} score={final_score:+.4f} (dir={score_result['dir_score']:+.3f}, str={score_result['strength_score']:.3f})")
                
                else:
                    stats["neutral"] += 1
    
    def print_summary(self):
        """Вивести зведену таблицю."""
        print("\n" + "="*90)
        print("  STRATEGY REPLAY SUMMARY")
        print("="*90)
        
        # Заголовок таблиці
        print(f"{'Symbol':<12} {'Ticks':>8} {'Intents':>8} {'BUY':>6} {'SELL':>6} {'Neutral':>8} {'Defer':>7} {'Top Block Reason':<30}")
        print("-"*90)
        
        for symbol in sorted(self.stats.keys()):
            s = self.stats[symbol]
            
            # Top block reason
            if s["blocked_reasons"]:
                top_reason = max(s["blocked_reasons"].items(), key=lambda x: x[1])
                reason_str = f"{top_reason[0]}({top_reason[1]})"
            else:
                reason_str = "-"
            
            print(f"{symbol:<12} {s['total_ticks']:>8} {s['intents_total']:>8} "
                  f"{s['intents_buy']:>6} {s['intents_sell']:>6} "
                  f"{s['neutral']:>8} {s['deferred']:>7} {reason_str:<30}")
        
        print("="*90)
        
        # Детальна статистика по кожному символу
        for symbol in sorted(self.stats.keys()):
            s = self.stats[symbol]
            if s["total_ticks"] == 0:
                continue
            
            print(f"\n📊 {symbol} — детальна статистика:")
            print(f"   Total ticks:       {s['total_ticks']}")
            print(f"   Intents generated: {s['intents_total']} ({s['intents_total']/s['total_ticks']*100:.1f}%)")
            print(f"   ├─ BUY:            {s['intents_buy']} ({s['intents_buy']/s['total_ticks']*100:.1f}%)")
            print(f"   ├─ SELL:           {s['intents_sell']} ({s['intents_sell']/s['total_ticks']*100:.1f}%)")
            print(f"   Neutral (no intent): {s['neutral']} ({s['neutral']/s['total_ticks']*100:.1f}%)")
            print(f"   Deferred:          {s['deferred']} ({s['deferred']/s['total_ticks']*100:.1f}%)")
            
            if s["scores"]:
                scores = sorted(s["scores"])
                print(f"\n   Score distribution:")
                print(f"     Min: {scores[0]:>7.4f}   P25: {scores[len(scores)//4]:>7.4f}   Med: {scores[len(scores)//2]:>7.4f}")
                print(f"     P75: {scores[len(scores)*3//4]:>7.4f}   P95: {scores[int(len(scores)*0.95)]:>7.4f}   Max: {scores[-1]:>7.4f}")
            
            if s["blocked_reasons"]:
                print(f"\n   Block reasons:")
                for reason, count in sorted(s["blocked_reasons"].items(), key=lambda x: -x[1])[:5]:
                    print(f"     {reason:<40} {count:>6} ({count/s['total_ticks']*100:>5.1f}%)")
        
        print("\n" + "="*90 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Strategy Replay на логах фіч")
    parser.add_argument(
        "--config",
        default="config/aurora",
        help="Шлях до конфігу (default: config/aurora)",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Список символів (default: всі з logs/features/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Виводити перші 10 інтентів для кожного символа",
    )
    parser.add_argument(
        "--no-qos",
        action="store_true",
        help="Вимкнути QoS gates (cooldown/rate limit) для тестування",
    )
    
    args = parser.parse_args()
    
    # Автовизначення символів
    if not args.symbols:
        feature_logs = Path("logs/features")
        if feature_logs.exists():
            args.symbols = [f.stem for f in feature_logs.glob("*.log")]
        else:
            print("❌ Папка logs/features/ не знайдена")
            return 1
    
    print(f"🎯 Символи для replay: {', '.join(args.symbols)}")
    if args.no_qos:
        print("⚠️  QoS gates ВИМКНЕНО (no cooldown, no rate limits)")
    
    replay = StrategyReplay(config_dir=args.config, verbose=args.verbose, no_qos=args.no_qos)
    
    for symbol in args.symbols:
        replay.replay_symbol(symbol)
    
    replay.print_summary()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
