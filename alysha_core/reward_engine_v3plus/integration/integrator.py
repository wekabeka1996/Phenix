"""
ALYSHA Integration Adapter для RLX Bridge
========================================

Интегрирует типизированную систему RLX Bridge с существующим
ALYSHA reward engine через обновленный PPO адаптер.

Ключевые функции:
- Бесшовная интеграция RLXContext с ALYSHA
- Fallback на legacy dict-based формат
- Комплексная валидация и error handling
- Мониторинг производительности конвертации
"""

from typing import Dict, Any, Optional, Union, Tuple, List
import logging
import numpy as np
from datetime import datetime
import traceback

from .rlx_bridge import (
    RLXContext,
    RLXToAlyshaConverter,
    PortfolioState,
    MarketState,
    ActionContext,
    MarketRegime,
    ActionType,
    convert_rlx_to_alysha,
)

# Config-driven defaults to avoid hardcoded parameters
try:
    from core.utils.canonical_config import get_config_with_fallback as _get_cfg
except Exception:

    def _get_cfg(*args, **kwargs):  # type: ignore
        return None


# Импорт существующего ALYSHA адаптера
try:
    from ..adapters.ppo_adapter import RewardEngineAPIV3Plus

    ALYSHA_ADAPTER_AVAILABLE = True
except ImportError as e:
    logging.warning(f"ALYSHA RewardEngineAPIV3Plus not available: {e}")
    ALYSHA_ADAPTER_AVAILABLE = False

logger = logging.getLogger(__name__)


class RLXAlyshaIntegrator:
    """
    Главный интегратор RLX-ALYSHA

    Управляет конвертацией данных между PPO агентом (RLX) и ALYSHA reward engine,
    обеспечивая типизированный и безопасный обмен данными с fallback механизмами.
    """

    def __init__(
        self,
        ppo_adapter: Optional["RewardEngineAPIV3Plus"] = None,
        enable_legacy_fallback: bool = True,
        strict_validation: bool = True,
        performance_monitoring: bool = True,
    ):
        """
        Инициализация интегратора

        Args:
            ppo_adapter: Существующий PPO адаптер ALYSHA (опционально)
            enable_legacy_fallback: Включить fallback на dict-based формат
            strict_validation: Включить строгую валидацию
            performance_monitoring: Включить мониторинг производительности
        """
        self.ppo_adapter = ppo_adapter
        self.enable_legacy_fallback = enable_legacy_fallback
        self.strict_validation = strict_validation
        self.performance_monitoring = performance_monitoring

        # Инициализация конвертера
        self.converter = RLXToAlyshaConverter(
            enable_strict_validation=strict_validation,
            enable_fallback=True,  # Всегда включен для безопасности
            log_conversions=performance_monitoring,
        )

        # Статистика интеграции
        self.integration_stats = {
            "total_integrations": 0,
            "successful_integrations": 0,
            "legacy_fallbacks": 0,
            "conversion_errors": 0,
            "alysha_errors": 0,
            "performance_metrics": {
                "avg_conversion_time": 0.0,
                "max_conversion_time": 0.0,
                "total_conversion_time": 0.0,
            },
        }

        self.logger = logging.getLogger(f"{__name__}.RLXAlyshaIntegrator")
        self.logger.info(
            f"RLX-ALYSHA Integrator initialized with validation={strict_validation}, "
            f"legacy_fallback={enable_legacy_fallback}"
        )

    def process_rlx_context(
        self,
        rlx_context: Union[RLXContext, Dict[str, Any]],
        reward_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Главная функция обработки RLX контекста через ALYSHA

        Args:
            rlx_context: Типизированный RLX контекст или legacy dict
            reward_context: Дополнительный контекст для reward engine

        Returns:
            Tuple[reward, metadata] - Результат от ALYSHA
        """
        start_time = datetime.now() if self.performance_monitoring else None
        self.integration_stats["total_integrations"] += 1

        try:
            # Этап 1: Обработка входных данных
            processed_context = self._process_input_context(rlx_context)

            # Этап 2: Конвертация в ALYSHA формат
            state_data = self._convert_to_alysha_format(processed_context)

            # Этап 3: Вызов ALYSHA reward engine
            reward, metadata = self._call_alysha_engine(state_data, reward_context)

            # Этап 4: Пост-обработка результата
            final_reward, final_metadata = self._post_process_result(
                reward, metadata, processed_context
            )

            # Успешная интеграция
            self.integration_stats["successful_integrations"] += 1

            # Мониторинг производительности
            if self.performance_monitoring and start_time:
                self._update_performance_metrics(start_time)

            self.logger.debug(f"Successful RLX-ALYSHA integration: reward={final_reward}")

            return final_reward, final_metadata

        except Exception as e:
            self.logger.error(f"RLX-ALYSHA integration error: {e}")
            self.logger.debug(f"Integration error traceback: {traceback.format_exc()}")

            # Попытка emergency fallback
            return self._emergency_fallback(rlx_context, e)

    def _process_input_context(self, rlx_context: Union[RLXContext, Dict[str, Any]]) -> RLXContext:
        """Обработка и нормализация входного контекста"""

        if isinstance(rlx_context, RLXContext):
            # Уже типизированный контекст
            self.logger.debug("Processing typed RLX context")
            return rlx_context

        elif isinstance(rlx_context, dict):
            # Legacy dict-based контекст - конвертируем в RLX
            self.logger.debug("Converting legacy dict context to RLX")
            return self._convert_dict_to_rlx_context(rlx_context)

        else:
            raise TypeError(f"Unsupported context type: {type(rlx_context)}")

    def _convert_dict_to_rlx_context(self, dict_context: Dict[str, Any]) -> RLXContext:
        """Конвертация legacy dict в типизированный RLXContext"""

        try:
            # Извлечение данных портфеля (config-driven fallbacks)
            default_balance = _get_cfg("trading.initial_cash", fallback=None)
            default_portfolio = _get_cfg(
                "trading.defaults.portfolio_value", fallback=default_balance
            )
            default_available = _get_cfg(
                "trading.defaults.available_balance", fallback=default_balance
            )
            portfolio = PortfolioState(
                balance=dict_context.get(
                    "balance", float(default_balance) if default_balance is not None else 0.0
                ),
                position_size=dict_context.get("position_size", 0.0),
                position_value=dict_context.get("position_value", 0.0),
                available_balance=dict_context.get(
                    "available_balance",
                    float(default_available) if default_available is not None else 0.0,
                ),
                portfolio_value=dict_context.get(
                    "portfolio_value",
                    float(default_portfolio) if default_portfolio is not None else 0.0,
                ),
                unrealized_pnl=dict_context.get("unrealized_pnl", 0.0),
                realized_pnl=dict_context.get("realized_pnl", 0.0),
                total_pnl=dict_context.get("total_pnl", 0.0),
                margin_ratio=dict_context.get("margin_ratio", 0.0),
                leverage=dict_context.get("leverage", 1.0),
                drawdown=dict_context.get("drawdown", 0.0),
                max_drawdown=dict_context.get("max_drawdown", 0.0),
                entry_price=dict_context.get("entry_price", 0.0),
            )

            # Извлечение рыночных данных
            market = MarketState(
                current_price=dict_context.get("price", dict_context.get("current_price", 100.0)),
                open_price=dict_context.get("open_price", 100.0),
                high_price=dict_context.get("high_price", 100.0),
                low_price=dict_context.get("low_price", 100.0),
                close_price=dict_context.get("close_price", 100.0),
                volume=dict_context.get("volume", 1000.0),
                volatility=dict_context.get("volatility", 0.02),
                rsi=dict_context.get("rsi", 50.0),
                macd=dict_context.get("macd", 0.0),
                macd_signal=dict_context.get("macd_signal", 0.0),
                bb_upper=dict_context.get("bb_upper", 105.0),
                bb_lower=dict_context.get("bb_lower", 95.0),
                sma_10=dict_context.get("sma_10", 100.0),
                sma_50=dict_context.get("sma_50", 100.0),
                market_regime=self._parse_market_regime(dict_context.get("market_regime")),
                trend_strength=dict_context.get("trend_strength", 0.0),
                market_sentiment=dict_context.get("market_sentiment", 0.0),
            )

            # Извлечение данных действия
            action = ActionContext(
                action_type=self._parse_action_type(
                    dict_context.get("action_type", dict_context.get("action"))
                ),
                action_value=dict_context.get("action_value", 0.0),
                action_size=dict_context.get("action_size", 0.0),
                confidence=dict_context.get("confidence", 0.5),
                risk_score=dict_context.get("risk_score", 0.5),
                transaction_cost=dict_context.get("transaction_cost", 0.0),
                slippage=dict_context.get("slippage", 0.0),
                commission=dict_context.get("commission", 0.0),
                step=dict_context.get("step", 0),
                episode=dict_context.get("episode", 0),
                total_steps=dict_context.get("total_steps", 0),
            )

            # Создание RLX контекста
            rlx_context = RLXContext(
                portfolio=portfolio,
                market=market,
                action=action,
                timestamp=dict_context.get("timestamp", datetime.now()),
                episode_step=dict_context.get("episode_step", 0),
                previous_reward=dict_context.get("previous_reward", 0.0),
                is_terminal=dict_context.get("is_terminal", False),
                is_training=dict_context.get("is_training", True),
                is_evaluation=dict_context.get("is_evaluation", False),
            )

            # Добавление дополнительных данных
            if "features" in dict_context:
                rlx_context.features = np.asarray(dict_context["features"])

            if "observation" in dict_context:
                rlx_context.observation = np.asarray(dict_context["observation"])

            self.logger.debug(f"Successfully converted dict to RLX context")
            return rlx_context

        except Exception as e:
            self.logger.error(f"Error converting dict to RLX context: {e}")
            # Создание минимального безопасного контекста
            return RLXContext()

    def _parse_market_regime(self, regime_value: Any) -> MarketRegime:
        """Парсинг режима рынка"""
        if isinstance(regime_value, str):
            try:
                return MarketRegime(regime_value.lower())
            except ValueError:
                pass

        return MarketRegime.UNKNOWN

    def _parse_action_type(self, action_value: Any) -> ActionType:
        """Парсинг типа действия"""
        if isinstance(action_value, str):
            try:
                return ActionType(action_value.lower())
            except ValueError:
                pass
        elif isinstance(action_value, (int, float)):
            # Числовое представление действия
            if action_value > 0.1:
                return ActionType.BUY
            elif action_value < -0.1:
                return ActionType.SELL
            else:
                return ActionType.HOLD

        return ActionType.UNKNOWN

    def _convert_to_alysha_format(self, rlx_context: RLXContext) -> Dict[str, Any]:
        """Конвертация RLX контекста в формат ALYSHA"""
        try:
            state_data = self.converter.convert(rlx_context)
            self.logger.debug("Successfully converted RLX to ALYSHA format")
            return state_data

        except Exception as e:
            self.integration_stats["conversion_errors"] += 1
            self.logger.error(f"Conversion error: {e}")
            raise

    def _call_alysha_engine(
        self, state_data: Dict[str, Any], reward_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, Dict[str, Any]]:
        """Вызов ALYSHA reward engine"""

        if not ALYSHA_ADAPTER_AVAILABLE or self.ppo_adapter is None:
            self.logger.warning("ALYSHA adapter not available, using mock reward")
            return self._mock_alysha_call(state_data)

        try:
            # Подготовка контекста для ALYSHA
            full_context = state_data.copy()
            if reward_context:
                full_context.update(reward_context)

            # Вызов ALYSHA через адаптер
            if hasattr(self.ppo_adapter, "compute_reward"):
                result = self.ppo_adapter.compute_reward(full_context)

                # Извлекаем вознаграждение и метаданные из результата
                reward = result.get("reward", 0.0)
                metadata = result.get("trace", {})
                metadata["source"] = "alysha_adapter"
                metadata["context_size"] = len(full_context)
            else:
                raise AttributeError(
                    "PPO adapter has no reward computation method ('compute_reward')"
                )

            # Валидация результата
            if (
                not isinstance(reward, (int, float, np.number))
                or np.isnan(reward)
                or np.isinf(reward)
            ):
                raise ValueError(f"Invalid reward from ALYSHA: {reward}")

            self.logger.debug(f"ALYSHA computed reward: {reward}")
            return float(reward), metadata

        except Exception as e:
            self.integration_stats["alysha_errors"] += 1
            self.logger.error(f"ALYSHA engine error: {e}")
            raise

    def _mock_alysha_call(self, state_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Mock вызов ALYSHA для тестирования"""
        self.logger.info("Using mock ALYSHA reward calculation")

        # Простая reward логика для тестирования
        portfolio_return = state_data.get("portfolio_return", 0.0)
        risk_level = state_data.get("risk_level", 0.5)
        action_quality = state_data.get("action_quality", 0.5)

        # Mock reward: прибыльность - риск + качество действия
        mock_reward = portfolio_return * 0.5 - risk_level * 0.3 + action_quality * 0.2

        metadata = {
            "source": "mock_alysha",
            "portfolio_return": portfolio_return,
            "risk_level": risk_level,
            "action_quality": action_quality,
            "mock_calculation": True,
        }

        return float(mock_reward), metadata

    def _post_process_result(
        self, reward: float, metadata: Dict[str, Any], rlx_context: RLXContext
    ) -> Tuple[float, Dict[str, Any]]:
        """Пост-обработка результата от ALYSHA"""

        # Добавление метаданных о процессе
        enhanced_metadata = metadata.copy()
        enhanced_metadata.update(
            {
                "integration_timestamp": datetime.now().isoformat(),
                "rlx_episode_step": rlx_context.episode_step,
                "rlx_action_type": rlx_context.action.action_type.value,
                "rlx_portfolio_value": rlx_context.portfolio.portfolio_value,
                "converter_stats": self.converter.get_conversion_stats(),
            }
        )

        # Валидация финального reward
        if np.isnan(reward) or np.isinf(reward):
            self.logger.warning(f"Invalid final reward: {reward}, applying correction")
            reward = 0.0
            enhanced_metadata["reward_corrected"] = True

        # Логирование для анализа
        if self.performance_monitoring:
            self.logger.debug(
                f"Final reward: {reward}, metadata keys: {list(enhanced_metadata.keys())}"
            )

        return reward, enhanced_metadata

    def _emergency_fallback(
        self, original_context: Union[RLXContext, Dict[str, Any]], error: Exception
    ) -> Tuple[float, Dict[str, Any]]:
        """Emergency fallback при полном сбое интеграции"""

        self.logger.error(f"Emergency fallback activated due to: {error}")

        if self.enable_legacy_fallback and isinstance(original_context, dict):
            # Попытка legacy обработки
            try:
                self.integration_stats["legacy_fallbacks"] += 1
                return self._legacy_reward_calculation(original_context)
            except Exception as legacy_error:
                self.logger.error(f"Legacy fallback also failed: {legacy_error}")

        # Последний безопасный fallback
        emergency_metadata = {
            "emergency_fallback": True,
            "original_error": str(error),
            "timestamp": datetime.now().isoformat(),
            "fallback_type": "emergency_safe",
        }

        return 0.0, emergency_metadata

    def _legacy_reward_calculation(
        self, dict_context: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """Legacy расчет reward для совместимости"""
        # Простая legacy логика (config-driven defaults)
        default_balance = _get_cfg("trading.initial_cash", fallback=None)
        default_portfolio = _get_cfg("trading.defaults.portfolio_value", fallback=default_balance)
        base_value = float(default_portfolio) if default_portfolio is not None else 0.0

        portfolio_value = float(dict_context.get("portfolio_value", base_value))
        previous_value = float(dict_context.get("previous_portfolio_value", base_value))

        if previous_value > 0:
            reward = (portfolio_value - previous_value) / previous_value
        else:
            reward = 0.0

        metadata = {
            "source": "legacy_calculation",
            "portfolio_value": portfolio_value,
            "previous_value": previous_value,
            "calculation_type": "simple_return",
        }

        return reward, metadata

    def _update_performance_metrics(self, start_time: datetime) -> None:
        """Обновление метрик производительности"""

        conversion_time = (datetime.now() - start_time).total_seconds()

        metrics = self.integration_stats["performance_metrics"]
        metrics["total_conversion_time"] += conversion_time
        metrics["max_conversion_time"] = max(metrics["max_conversion_time"], conversion_time)

        total_integrations = self.integration_stats["total_integrations"]
        if total_integrations > 0:
            metrics["avg_conversion_time"] = metrics["total_conversion_time"] / total_integrations

    def get_integration_stats(self) -> Dict[str, Any]:
        """Получение статистики интеграции"""

        stats = self.integration_stats.copy()

        # Расчет дополнительных метрик
        total = stats["total_integrations"]
        if total > 0:
            stats["success_rate"] = stats["successful_integrations"] / total
            stats["legacy_fallback_rate"] = stats["legacy_fallbacks"] / total
            stats["conversion_error_rate"] = stats["conversion_errors"] / total
            stats["alysha_error_rate"] = stats["alysha_errors"] / total
        else:
            stats["success_rate"] = 0.0
            stats["legacy_fallback_rate"] = 0.0
            stats["conversion_error_rate"] = 0.0
            stats["alysha_error_rate"] = 0.0

        # Добавление статистики конвертера
        stats["converter_stats"] = self.converter.get_conversion_stats()

        return stats

    def reset_stats(self) -> None:
        """Сброс всей статистики"""

        self.integration_stats = {
            "total_integrations": 0,
            "successful_integrations": 0,
            "legacy_fallbacks": 0,
            "conversion_errors": 0,
            "alysha_errors": 0,
            "performance_metrics": {
                "avg_conversion_time": 0.0,
                "max_conversion_time": 0.0,
                "total_conversion_time": 0.0,
            },
        }

        self.converter.reset_stats()
        self.logger.info("Integration statistics reset")


# Глобальный интегратор для удобства использования
_global_integrator: Optional[RLXAlyshaIntegrator] = None


def get_global_integrator() -> RLXAlyshaIntegrator:
    """Получение глобального интегратора (singleton pattern)"""
    global _global_integrator

    if _global_integrator is None:
        _global_integrator = RLXAlyshaIntegrator()
        logger.info("Created global RLX-ALYSHA integrator")

    return _global_integrator


def set_global_integrator(integrator: RLXAlyshaIntegrator) -> None:
    """Установка кастомного глобального интегратора"""
    global _global_integrator
    _global_integrator = integrator
    logger.info("Set custom global RLX-ALYSHA integrator")


def process_ppo_context(
    context: Union[RLXContext, Dict[str, Any]], reward_context: Optional[Dict[str, Any]] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    Быстрая функция для обработки PPO контекста

    Args:
        context: RLX контекст или legacy dict
        reward_context: Дополнительный контекст

    Returns:
        Tuple[reward, metadata]
    """
    integrator = get_global_integrator()
    return integrator.process_rlx_context(context, reward_context)


def initialize_rlx_alysha_integration(
    ppo_adapter: Optional[Any] = None,
    strict_validation: bool = True,
    enable_legacy_fallback: bool = True,
) -> RLXAlyshaIntegrator:
    """
    Инициализация интеграции RLX-ALYSHA

    Args:
        ppo_adapter: PPO адаптер ALYSHA
        strict_validation: Строгая валидация
        enable_legacy_fallback: Legacy fallback

    Returns:
        Настроенный интегратор
    """
    integrator = RLXAlyshaIntegrator(
        ppo_adapter=ppo_adapter,
        enable_legacy_fallback=enable_legacy_fallback,
        strict_validation=strict_validation,
        performance_monitoring=True,
    )

    set_global_integrator(integrator)
    logger.info("RLX-ALYSHA integration initialized successfully")

    return integrator
