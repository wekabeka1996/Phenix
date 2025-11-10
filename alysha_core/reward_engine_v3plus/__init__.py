"""
ALYSHA-RE-V3+ Reward Engine

Розширена система винагород для торгового агента з підтримкою:
- Багатокомпонентної винагороди (PnL, Risk, Cost, Behavior, Information)
- Адаптивного контролю ваг залежно від ринкового режиму
- Нормалізації компонент
- Дискретних подій та формування поведінки
- Математично обґрунтованих формул згідно з роадмапом

Головні компоненти:
- RewardEngineV3Plus: Головний клас агрегації винагород
- Компоненти в ./components/: PnL, Risk, Cost, Behavior, Information, Event, Shaping
- AdaptiveWeightsManager: Управління адаптивними вагами
- Normalizers: Нормалізація компонент
"""

# Імпорти будуть додані після створення всіх компонент

__all__ = ['RewardEngineV3Plus', 'AdaptiveWeightsManager']

# Імпорти виконуються в runtime для уникнення циклічних залежностей
def get_reward_engine():
    from .main_engine import RewardEngineV3Plus
    return RewardEngineV3Plus

def get_adaptive_weights_manager():
    from .adaptive_weights_manager import AdaptiveWeightsManager  
    return AdaptiveWeightsManager
