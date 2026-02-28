#!/usr/bin/env python3
"""
Config Tuner - A/B тестування конфігів на логах фіч
====================================================

Використання:
    # Запустити на поточному конфігу (HEAD)
    python3 tools/config_tuner.py --mode current --symbols SOLUSDT ETHUSDT
    
    # Запустити на "доброму" конфігу (865bf5c)
    python3 tools/config_tuner.py --mode baseline --symbols SOLUSDT ETHUSDT
    
    # Порівняти обидва
    python3 tools/config_tuner.py --mode compare --symbols SOLUSDT ETHUSDT
    
    # Інтерактивний тюнінг (міняєш пороги/ваги в реальному часі)
    python3 tools/config_tuner.py --mode interactive --symbol SOLUSDT

Цей скрипт:
- Читає готові логи фіч з logs/features/*.log
- Прогоняє через scoring V2 (з direction/strength split)
- Рахує: скільки BUY/SELL/NEUTRAL, скільки DEFER (missing features)
- Показує розподіл score, контрибуції фіч
- Дає можливість швидко A/B тестувати зміни в конфігах
"""

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Додаємо кореневу директорію до path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
    compute_direction_strength_score,
)


class ConfigTuner:
    """A/B тестування конфігів на історичних логах фіч."""
    
    def __init__(self, config_mode: str = "current"):
        """
        Args:
            config_mode: 'current' (HEAD), 'baseline' (865bf5c), або 'custom'
        """
        self.config_mode = config_mode
        self.config = None
        self.stats = defaultdict(lambda: {
            "total": 0,
            "buy": 0,
            "sell": 0,
            "neutral": 0,
            "deferred": 0,
            "liquidity_blocked": 0,
            "scores": [],
            "feature_contribs": defaultdict(list),
        })
        
    def load_config(self, config_path: Optional[str] = None):
        """Завантажити конфіг."""
        if config_path:
            loader = ConfigLoader(config_path)
        else:
            # Дефолтний конфіг з config/aurora/
            loader = ConfigLoader("config/aurora")
        
        self.config = loader.load()
        print(f"✅ Конфіг завантажено: trading_mode={self.config.trading_mode}")
        
        # Виводимо ключові параметри скорингу
        decision_cfg = self.config.strategies.aurora.decision
        print(f"  signal_threshold: {decision_cfg.signal_threshold}")
        print(f"  neutral_threshold: {decision_cfg.neutral_threshold}")
        print(f"  scoring_version: {getattr(decision_cfg, 'scoring_version', 'v1')}")
        print(f"  normalize_signals_mode: {decision_cfg.signals.normalize_signals_mode}")
        
    def load_features_log(self, symbol: str) -> List[Dict[str, Any]]:
        """Завантажити лог фіч для символа."""
        log_path = Path(f"logs/features/{symbol}.log")
        if not log_path.exists():
            raise FileNotFoundError(f"Лог не знайдено: {log_path}")
        
        features = []
        with log_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    features.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️  Помилка парсингу JSON на рядку {i}: {e}")
                    continue
        
        print(f"📊 Завантажено {len(features)} записів фіч для {symbol}")
        return features
    
    def replay_symbol(self, symbol: str, features: List[Dict[str, Any]]):
        """Прогнати replay для одного символа."""
        decision_cfg = self.config.strategies.aurora.decision
        
        # Отримуємо ваги/нейтралі/essential з конфігу
        signal_weights = decision_cfg.signal_weights.model_dump()
        feature_neutrals = getattr(decision_cfg, "feature_neutrals", {})
        essential_features = getattr(decision_cfg, "essential_features", [])
        
        # Direction/strength конфіг
        ds_cfg = decision_cfg.direction_strength_scoring
        directional_features = list(ds_cfg.directional_features)
        strength_features = list(ds_cfg.strength_features)
        strength_alpha = float(ds_cfg.strength_alpha)
        strength_cap = float(ds_cfg.strength_cap)
        
        # Режими нормалізації
        normalize_mode = str(decision_cfg.signals.normalize_signals_mode)
        
        # Пороги
        signal_threshold = Decimal(str(decision_cfg.signal_threshold))
        neutral_threshold = Decimal(str(decision_cfg.neutral_threshold))
        
        # Liquidity gate
        liq_gate_cfg = getattr(decision_cfg, "liquidity_gate", None)
        liq_gate_enabled = liq_gate_cfg.enabled if liq_gate_cfg else False
        liq_kappa_min = float(liq_gate_cfg.kappa_min) if liq_gate_cfg else 0.0
        
        stats = self.stats[symbol]
        
        for i, feat_dict in enumerate(features):
            stats["total"] += 1
            
            # Liquidity gate (якщо enabled)
            if liq_gate_enabled:
                kappa_raw = feat_dict.get("liquidity_kappa")
                if kappa_raw is None:
                    stats["deferred"] += 1
                    continue
                kappa = float(kappa_raw)
                if kappa < liq_kappa_min:
                    stats["liquidity_blocked"] += 1
                    continue
            
            # Створюємо mock readiness (всі фічі "ready", крім відсутніх)
            readiness = {k: True for k in feat_dict.keys()}
            
            # Normalize delta_price (як у production)
            price = Decimal(str(feat_dict.get("price", 0)))
            dp_raw = Decimal(str(feat_dict.get("delta_price", 0)))
            dp_cap_pct = Decimal("0.02")  # з конфігу signals.delta_price_cap_pct
            
            if price > 0 and dp_cap_pct > 0:
                dp_pct = dp_raw / price
                dp_pct = max(-dp_cap_pct, min(dp_pct, dp_cap_pct))
                dp_norm = dp_pct / dp_cap_pct  # [-1, 1]
            else:
                dp_norm = Decimal("0")
            
            # Підміняємо delta_price на нормалізовану версію
            feat_eval = dict(feat_dict)
            feat_eval["delta_price"] = float(dp_norm)
            
            # Рахуємо direction/strength score
            ds_score = compute_direction_strength_score(
                features=feat_eval,
                weights=signal_weights,
                neutrals=feature_neutrals,
                readiness=readiness,
                essential_features=set(essential_features),
                normalize_mode=normalize_mode,
                directional_features=directional_features,
                strength_features=strength_features,
                strength_alpha=strength_alpha,
                strength_cap=strength_cap,
                symbol=symbol,
            )
            
            if ds_score.deferred:
                stats["deferred"] += 1
                continue
            
            final_score = ds_score.final_score
            stats["scores"].append(float(final_score))
            
            # Збираємо контрибуції фіч
            for feat, contrib in ds_score.dir_result.contribs.items():
                stats["feature_contribs"][feat].append(contrib)
            
            # Визначаємо side
            if final_score >= signal_threshold:
                stats["buy"] += 1
            elif final_score <= -signal_threshold:
                stats["sell"] += 1
            else:
                stats["neutral"] += 1
    
    def print_summary(self):
        """Вивести зведену статистику."""
        print("\n" + "="*70)
        print(f"  CONFIG TUNER SUMMARY — mode={self.config_mode}")
        print("="*70)
        
        for symbol, stats in self.stats.items():
            print(f"\n[{symbol}]")
            print(f"  Total records:      {stats['total']}")
            print(f"  ├─ BUY signals:     {stats['buy']:>6} ({stats['buy']/stats['total']*100:>5.1f}%)")
            print(f"  ├─ SELL signals:    {stats['sell']:>6} ({stats['sell']/stats['total']*100:>5.1f}%)")
            print(f"  ├─ NEUTRAL:         {stats['neutral']:>6} ({stats['neutral']/stats['total']*100:>5.1f}%)")
            print(f"  ├─ DEFERRED:        {stats['deferred']:>6} ({stats['deferred']/stats['total']*100:>5.1f}%)")
            print(f"  └─ LIQ_BLOCKED:     {stats['liquidity_blocked']:>6} ({stats['liquidity_blocked']/stats['total']*100:>5.1f}%)")
            
            if stats["scores"]:
                scores = stats["scores"]
                print(f"\n  Score distribution:")
                print(f"    Min:  {min(scores):>7.4f}")
                print(f"    P05:  {sorted(scores)[int(len(scores)*0.05)]:>7.4f}")
                print(f"    P25:  {sorted(scores)[int(len(scores)*0.25)]:>7.4f}")
                print(f"    Med:  {sorted(scores)[int(len(scores)*0.50)]:>7.4f}")
                print(f"    P75:  {sorted(scores)[int(len(scores)*0.75)]:>7.4f}")
                print(f"    P95:  {sorted(scores)[int(len(scores)*0.95)]:>7.4f}")
                print(f"    Max:  {max(scores):>7.4f}")
                
            # Top-5 контрибуторів (по абсолютному впливу)
            if stats["feature_contribs"]:
                print(f"\n  Top-5 feature contributors (by avg abs contribution):")
                contrib_avg = {
                    feat: sum(abs(c) for c in contribs) / len(contribs)
                    for feat, contribs in stats["feature_contribs"].items()
                    if contribs
                }
                for feat, avg in sorted(contrib_avg.items(), key=lambda x: -x[1])[:5]:
                    print(f"    {feat:20s}: {avg:>7.4f}")
        
        print("\n" + "="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Config Tuner — A/B тестування конфігів на логах фіч"
    )
    parser.add_argument(
        "--mode",
        choices=["current", "baseline", "compare", "interactive"],
        default="current",
        help="Режим роботи: current=поточний HEAD, baseline=865bf5c, compare=порівняти обидва",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SOLUSDT", "ETHUSDT", "BTCUSDT"],
        help="Список символів для replay",
    )
    parser.add_argument(
        "--config",
        help="Шлях до custom конфігу (опціонально)",
    )
    
    args = parser.parse_args()
    
    if args.mode == "compare":
        print("🔄 Режим COMPARE: запускаємо обидва конфіги...\n")
        
        # Поточний конфіг
        print("📌 Запуск на ПОТОЧНОМУ конфігу (HEAD):")
        tuner_current = ConfigTuner("current")
        tuner_current.load_config(args.config)
        
        for symbol in args.symbols:
            features = tuner_current.load_features_log(symbol)
            tuner_current.replay_symbol(symbol, features)
        
        tuner_current.print_summary()
        
        # TODO: baseline конфіг через git checkout або окремий файл
        print("\n⚠️  Baseline (865bf5c) режим поки не реалізовано автоматично.")
        print("    Запусти вручну після `git checkout 865bf5c` або підготуй копію конфігу.\n")
        
    else:
        tuner = ConfigTuner(args.mode)
        tuner.load_config(args.config)
        
        for symbol in args.symbols:
            features = tuner.load_features_log(symbol)
            tuner.replay_symbol(symbol, features)
        
        tuner.print_summary()


if __name__ == "__main__":
    main()
