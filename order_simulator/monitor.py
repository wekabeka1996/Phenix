#!/usr/bin/env python3
"""
ORDER SIMULATOR - Утиліта для тестування 5 варіантів TP/SL паралельно

Система працює так:
1. Читає event_chain.log та чекає на EVT:ORDER_OPENED
2. Коли нове замовлення відкрилося → створює 5 паралельних симульованих позицій
   з різними TP/SL варіантами
3. Читає ціни з логів (або з API) і оновлює статус кожної позиції
4. Коли TP/SL хітається → записує результат (WIN/LOSS)
5. Зберігає все в results.jsonl для аналізу
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from decimal import Decimal
from typing import Dict, Any, List, Optional
import threading

# ============================================================================
# SETUP
# ============================================================================

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
ACTIVE_ORDERS_FILE = BASE_DIR / "active_orders.json"
RESULTS_FILE = BASE_DIR / "results.jsonl"
LOG_SOURCE = BASE_DIR.parent / "logs" / "event_chain.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / "simulation.log"),
        logging.StreamHandler()
    ]
)
LOG = logging.getLogger(__name__)

# ============================================================================
# DATA MODELS
# ============================================================================

class SimulatedPosition:
    """Одна симульована позиція (один варіант TP/SL)"""

    def __init__(self, order_id: str, symbol: str, entry_price: float,
                 variant_id: str, variant_config: Dict[str, Any]):
        self.order_id = order_id
        self.symbol = symbol
        self.entry_price = entry_price
        self.variant_id = variant_id
        self.variant_config = variant_config

        # Розраховуємо TP/SL на основі варіанту
        self.tp_price = self._calc_tp()
        self.sl_price = self._calc_sl()

        self.status = "ACTIVE"  # ACTIVE, WIN, LOSS
        self.pnl = None
        self.close_price = None
        self.close_timestamp = None
        self.created_at = datetime.utcnow().isoformat()

    def _calc_tp(self) -> float:
        """TP = Entry + (SL_bps × ratio)"""
        base_sl_bps = 50  # від конфігу
        tp_ratio = self.variant_config["tp_ratio"]
        tp_bps = base_sl_bps * tp_ratio
        return self.entry_price * (1.0 + tp_bps / 10000.0)

    def _calc_sl(self) -> float:
        """SL = Entry - (SL_bps × ratio)"""
        base_sl_bps = 50  # від конфігу
        sl_ratio = self.variant_config["sl_ratio"]
        sl_bps = base_sl_bps * sl_ratio
        return self.entry_price * (1.0 - sl_bps / 10000.0)

    def check_price(self, current_price: float) -> Optional[str]:
        """Перевіряє чи хітнулася TP або SL. Повертає 'WIN' / 'LOSS' / None"""
        if self.status != "ACTIVE":
            return None

        if current_price >= self.tp_price:
            self.status = "WIN"
            self.close_price = self.tp_price
            self.pnl = (self.tp_price - self.entry_price)
            self.close_timestamp = datetime.utcnow().isoformat()
            return "WIN"

        elif current_price <= self.sl_price:
            self.status = "LOSS"
            self.close_price = self.sl_price
            self.pnl = (self.sl_price - self.entry_price)
            self.close_timestamp = datetime.utcnow().isoformat()
            return "LOSS"

        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "variant_id": self.variant_id,
            "variant_name": self.variant_config.get("name"),
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "tp_price": round(self.tp_price, 8),
            "sl_price": round(self.sl_price, 8),
            "status": self.status,
            "pnl": round(self.pnl, 8) if self.pnl else None,
            "close_price": round(self.close_price, 8) if self.close_price else None,
            "created_at": self.created_at,
            "closed_at": self.close_timestamp
        }


class OrderSimulator:
    """Головна система для симуляції ордерів"""

    def __init__(self, config_file: Path):
        with open(config_file) as f:
            self.config = json.load(f)

        self.active_positions: Dict[str, List[SimulatedPosition]] = {}
        self.completed_positions: List[SimulatedPosition] = []
        self.last_log_position = 0

        LOG.info("OrderSimulator initialized")

    def load_active_positions(self):
        """Завантажує активні позиції зі збереженого файлу"""
        if ACTIVE_ORDERS_FILE.exists():
            with open(ACTIVE_ORDERS_FILE) as f:
                data = json.load(f)
                for order_id, variants in data.items():
                    self.active_positions[order_id] = []
                    for variant_data in variants:
                        pos = SimulatedPosition(
                            order_id=order_id,
                            symbol=variant_data["symbol"],
                            entry_price=variant_data["entry_price"],
                            variant_id=variant_data["variant_id"],
                            variant_config=self._get_variant_config(variant_data["variant_id"])
                        )
                        pos.status = variant_data["status"]
                        self.active_positions[order_id].append(pos)
            LOG.info(f"Loaded {len(self.active_positions)} active orders")

    def save_active_positions(self):
        """Зберігає активні позиції"""
        data = {}
        for order_id, positions in self.active_positions.items():
            data[order_id] = [p.to_dict() for p in positions]

        with open(ACTIVE_ORDERS_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def _get_variant_config(self, variant_id: str) -> Dict[str, Any]:
        """Знаходить конфіг варіанту по ID"""
        for variant in self.config["variants"]:
            if variant["id"] == variant_id:
                return variant
        raise ValueError(f"Variant {variant_id} not found")

    def create_order(self, order_id: str, symbol: str, entry_price: float):
        """Створює 5 паралельних позицій для нового ордера"""
        positions = []

        for variant in self.config["variants"]:
            pos = SimulatedPosition(
                order_id=order_id,
                symbol=symbol,
                entry_price=entry_price,
                variant_id=variant["id"],
                variant_config=variant
            )
            positions.append(pos)

        self.active_positions[order_id] = positions
        LOG.info(f"Created order {order_id} with 5 variants: {entry_price} {symbol}")

        return positions

    def update_price(self, symbol: str, current_price: float):
        """Оновлює ціну для всіх активних позицій по символу"""
        updated_count = 0

        for order_id, positions in self.active_positions.items():
            for pos in positions:
                if pos.symbol == symbol and pos.status == "ACTIVE":
                    result = pos.check_price(current_price)
                    if result:
                        updated_count += 1
                        self._save_result(pos, result)
                        LOG.info(f"{result}: {pos.variant_id} - {symbol} @ {current_price}")

        if updated_count > 0:
            self.save_active_positions()

        return updated_count

    def _save_result(self, position: SimulatedPosition, result: str):
        """Записує результат в results.jsonl"""
        result_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "order_id": position.order_id,
            "variant_id": position.variant_id,
            "variant_name": position.variant_config.get("name"),
            "symbol": position.symbol,
            "entry_price": position.entry_price,
            "tp_price": position.tp_price,
            "sl_price": position.sl_price,
            "close_price": position.close_price,
            "result": result,
            "pnl": position.pnl
        }

        with open(RESULTS_FILE, 'a') as f:
            f.write(json.dumps(result_record) + '\n')

        self.completed_positions.append(position)

    def read_log_events(self):
        """Читає нові события з event_chain.log"""
        if not LOG_SOURCE.exists():
            LOG.warning(f"Log file not found: {LOG_SOURCE}")
            return

        with open(LOG_SOURCE, 'r') as f:
            f.seek(self.last_log_position)

            for line in f:
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)
                    self._process_event(event)
                except json.JSONDecodeError:
                    continue

            self.last_log_position = f.tell()

    def _process_event(self, event: Dict[str, Any]):
        """Обробляє одну событие з логу"""
        event_type = event.get("event_type") or event.get("event")

        # Читаємо відкриття нових ордерів
        if event_type == "EVT:ORDER_OPENED":
            symbol = event.get("symbol")
            entry_price = event.get("entry_price")
            rid = event.get("rid", "unknown")

            if symbol and entry_price:
                # Якщо ордер по цьому символу вже в симуляції, пропускаємо
                if rid not in self.active_positions:
                    self.create_order(rid, symbol, float(entry_price))

        # Читаємо ціни для оновлення позицій
        elif event_type in ["EVT:PRICE_UPDATE", "EVT:MARKET_DATA"]:
            symbol = event.get("symbol")
            price = event.get("price") or event.get("markPrice")

            if symbol and price:
                self.update_price(symbol, float(price))

    def get_stats(self) -> Dict[str, Any]:
        """Повертає статистику"""
        total_wins = sum(1 for p in self.completed_positions if p.status == "WIN")
        total_loss = sum(1 for p in self.completed_positions if p.status == "LOSS")
        total_pnl = sum(p.pnl for p in self.completed_positions if p.pnl)

        active_count = sum(len(pos) for pos in self.active_positions.values())

        return {
            "active_orders": len(self.active_positions),
            "active_positions": active_count,
            "completed": len(self.completed_positions),
            "wins": total_wins,
            "losses": total_loss,
            "win_rate": (total_wins / (total_wins + total_loss) * 100) if (total_wins + total_loss) > 0 else 0,
            "total_pnl": total_pnl
        }

    def run(self, interval_sec: int = 2):
        """Головний loop - читає логи і оновлює позиції"""
        LOG.info(f"Starting OrderSimulator (poll interval: {interval_sec}s)")

        self.load_active_positions()

        try:
            while True:
                self.read_log_events()
                self.save_active_positions()

                stats = self.get_stats()
                LOG.info(f"Stats: {stats}")

                time.sleep(interval_sec)

        except KeyboardInterrupt:
            LOG.info("Shutting down...")
            self.save_active_positions()

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    sim = OrderSimulator(CONFIG_FILE)

    poll_interval = sim.config.get("poll_interval_sec", 2)
    sim.run(interval_sec=poll_interval)
