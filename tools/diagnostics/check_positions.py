#!/usr/bin/env python3
"""
Перевірка поточних позицій на Binance TESTNET
"""

import asyncio
import os
import json
from apps.reference.adapters.binance_adapter import BinanceAdapter

# Завантаження змінних середовища
try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass  # dotenv не обов'язковий якщо змінні вже встановлені


async def check_testnet_positions():
    """Перевірити поточні позиції на testnet"""

    print("🔍 Перевірка позицій на Binance TESTNET...")

    # Ініціалізація адаптера для testnet
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        print("❌ BINANCE_TESTNET_API_KEY або BINANCE_TESTNET_API_SECRET не встановлені")
        print(f"  API_KEY: {'✅' if api_key else '❌'}")
        print(f"  API_SECRET: {'✅' if api_secret else '❌'}")
        return

    adapter = BinanceAdapter(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://testnet.binancefuture.com"
    )

    try:
        # Отримати позиції
        positions = await adapter.get_open_positions()
        print(f"📊 Знайдено {len(positions)} позицій:")

        sol_position = None
        eth_position = None

        for pos in positions:
            symbol = pos.get("symbol", "")
            position_amt = float(pos.get("positionAmt", 0))
            entry_price = float(pos.get("entryPrice", 0))
            unrealized_pnl = float(pos.get("unrealizedProfit", 0))

            if abs(position_amt) > 0.0001:  # Фільтруємо нулі
                print(
                    f"  {symbol}: {position_amt} @ {entry_price} (PNL: {unrealized_pnl})")

                if symbol == "SOLUSDT":
                    sol_position = position_amt
                elif symbol == "ETHUSDT":
                    eth_position = position_amt

        # Перевірка заявлених позицій користувача
        print("\n🔍 Перевірка заявлених позицій:")
        print(
            f"  SOL: {'✅' if sol_position and abs(sol_position - 1.0) < 0.1 else '❌'} (очікувано: 1.0, фактично: {sol_position})")
        print(f"  ETH: {'✅' if eth_position and abs(eth_position - 0.047) < 0.01 else '❌'} (очікувано: 0.047, фактично: {eth_position})")

        # Детальна інформація
        if sol_position or eth_position:
            print("\n📋 Деталі позицій:")
            if sol_position:
                print(f"  SOLUSDT: позиція = {sol_position}")
            if eth_position:
                print(f"  ETHUSDT: позиція = {eth_position}")
        else:
            print("\n❌ Жодних відкритих позицій не знайдено")

    except Exception as e:
        print(f"❌ Помилка при отриманні позицій: {e}")

if __name__ == "__main__":
    asyncio.run(check_testnet_positions())
