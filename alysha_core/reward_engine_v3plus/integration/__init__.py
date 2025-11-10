"""
RLX-ALYSHA Integration Bridge
============================

Типизированная система обмена данными между PPO агентом (RLX) и ALYSHA reward engine.

Основные компоненты:
- RLXContext: Типизированный контракт данных от PPO
- RLXToAlyshaConverter: Безопасный конвертер с обработкой ошибок  
- RLXAlyshaIntegrator: Главный интегратор с fallback механизмами
- Утилитарные функции для быстрого использования

Использование:
    # Простая конвертация
    from alysha_core.reward_engine_v3plus.integration import process_ppo_context
    reward, metadata = process_ppo_context(rlx_context)
    
    # Полная настройка
    from alysha_core.reward_engine_v3plus.integration import initialize_rlx_alysha_integration
    integrator = initialize_rlx_alysha_integration(ppo_adapter=my_adapter)
"""

# Основные классы и типы
from .rlx_bridge import (
    # Основные dataclasses
    RLXContext,
    PortfolioState,
    MarketState,
    ActionContext,
    
    # Enums
    MarketRegime,
    ActionType,
    
    # Конвертер
    RLXToAlyshaConverter,
    
    # Утилитарные функции
    convert_rlx_to_alysha,
    validate_rlx_context,
    create_sample_rlx_context
)

# Интегратор
from .integrator import (
    RLXAlyshaIntegrator,
    get_global_integrator,
    set_global_integrator,
    process_ppo_context,
    initialize_rlx_alysha_integration
)

# Версия модуля
__version__ = "1.0.0"

# Основные экспорты для удобства
__all__ = [
    # Основные классы
    'RLXContext',
    'PortfolioState', 
    'MarketState',
    'ActionContext',
    'MarketRegime',
    'ActionType',
    
    # Конвертация
    'RLXToAlyshaConverter',
    'convert_rlx_to_alysha',
    'validate_rlx_context',
    
    # Интеграция
    'RLXAlyshaIntegrator',
    'process_ppo_context',
    'initialize_rlx_alysha_integration',
    
    # Утилиты
    'get_global_integrator',
    'set_global_integrator',
    'create_sample_rlx_context'
]

# Логирование инициализации модуля
import logging
logger = logging.getLogger(__name__)
logger.info(f"RLX-ALYSHA Integration Bridge v{__version__} loaded successfully")


# Быстрая настройка для common use cases
def quick_setup(ppo_adapter=None, strict_mode: bool = True) -> RLXAlyshaIntegrator:
    """
    Быстрая настройка интеграции для стандартных случаев
    
    Args:
        ppo_adapter: ALYSHA PPO адаптер (опционально)
        strict_mode: Включить строгую валидацию
        
    Returns:
        Настроенный интегратор
    """
    return initialize_rlx_alysha_integration(
        ppo_adapter=ppo_adapter,
        strict_validation=strict_mode,
        enable_legacy_fallback=True
    )


def dev_setup(mock_alysha: bool = True) -> RLXAlyshaIntegrator:
    """
    Настройка для разработки и тестирования
    
    Args:
        mock_alysha: Использовать mock ALYSHA вместо реального
        
    Returns:
        Интегратор для разработки
    """
    adapter = None if mock_alysha else "auto"  # auto будет искать реальный адаптер
    
    return initialize_rlx_alysha_integration(
        ppo_adapter=adapter,
        strict_validation=False,  # Более мягкая валидация для dev
        enable_legacy_fallback=True
    )


def production_setup(ppo_adapter, monitoring: bool = True) -> RLXAlyshaIntegrator:
    """
    Настройка для production окружения
    
    Args:
        ppo_adapter: Реальный ALYSHA PPO адаптер (обязательно)
        monitoring: Включить мониторинг производительности
        
    Returns:
        Production-ready интегратор
    """
    if ppo_adapter is None:
        raise ValueError("PPO adapter is required for production setup")
    
    integrator = RLXAlyshaIntegrator(
        ppo_adapter=ppo_adapter,
        enable_legacy_fallback=True,
        strict_validation=True,
        performance_monitoring=monitoring
    )
    
    set_global_integrator(integrator)
    logger.info("Production RLX-ALYSHA integration configured")
    
    return integrator


# Shortcut для самых частых операций
def simple_convert(rlx_context, **kwargs) -> dict:
    """Простая конвертация без полной интеграции"""
    return convert_rlx_to_alysha(rlx_context, **kwargs)


def simple_process(context, reward_context=None):
    """Простая обработка с автоматической настройкой"""
    return process_ppo_context(context, reward_context)
