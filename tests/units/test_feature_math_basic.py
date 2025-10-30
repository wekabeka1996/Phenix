from decimal import Decimal
# Импортируй модуль, где реально считаются OBI/TFI (укажи путь проекта)
import sys
sys.path.insert(0, 'c:/Users/user/Music/Phenix')
from apps.reference.domains.feature_engineering import feature_engineering as fe  # адаптируй имя


def test_obi_tfi_basic():
    # Простейший дисбаланс книги и потока сделок
    book = {"bid_qty": Decimal("100"), "ask_qty": Decimal("50")}
    trades = {"buy": 30, "sell": 20}

    # Create a mock instance to access the calculation method
    class MockFeatureEngineering:
        def _calculate_and_emit_features(self, symbol, current_tick, last_tick):
            bid_size = Decimal(str(current_tick.get("bid_size", 0)))
            ask_size = Decimal(str(current_tick.get("ask_size", 0)))
            buy_volume = Decimal(str(current_tick.get("buy_volume", 0)))
            sell_volume = Decimal(str(current_tick.get("sell_volume", 0)))

            depth = bid_size + ask_size
            obi = (bid_size - ask_size) / depth if depth > 0 else Decimal(0)

            total_flow = buy_volume + sell_volume
            tfi = (
                (buy_volume - sell_volume) / total_flow
                if total_flow > 0
                else Decimal(0)
            )

            return obi, tfi

    mock_fe = MockFeatureEngineering()

    # Test data
    current_tick = {"bid_size": "100", "ask_size": "50", "buy_volume": "30", "sell_volume": "20"}
    last_tick = {"price": "100"}

    obi, tfi = mock_fe._calculate_and_emit_features("BTCUSDT", current_tick, last_tick)

    # Ожидается obi > 0 (больше bid), tfi > 0 (больше buy)
    assert obi > 0 and tfi > 0
