"""
RLX-ALYSHA Bridge: Typed Data Exchange System
===========================================

Забезпечує типізований та безпечний обмін даними між PPO агентом (RLX)
та ALYSHA reward engine. Замінює крихкий dict-based підхід на надійні
dataclass контракти з валідацією та fallback механізмами.

Key Components:
- RLXContext: Типізований контракт даних від PPO
- RLXToAlyshaConverter: Безпечний конвертер з обробкою помилок
- StateData fallback: Мінімально безпечні дані при збоях
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Union, List, Tuple
from enum import Enum
import logging
import numpy as np
from datetime import datetime
import warnings

logger = logging.getLogger(__name__)

# Config access for eliminating hardcoded balance defaults
try:
    from core.utils.canonical_config import get_config_with_fallback
except Exception:  # soft-fallback to avoid hard dependency loops in tests

    def get_config_with_fallback(*args, **kwargs):  # type: ignore
        return None


class MarketRegime(Enum):
    """Режими ринку для контекстної оцінки ризику"""

    NORMAL = "normal"
    BULL = "bull"
    BEAR = "bear"
    CRISIS = "crisis"
    VOLATILITY = "volatility"
    FLAT = "flat"
    UNKNOWN = "unknown"


class ActionType(Enum):
    """Типи дій PPO агента"""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    UNKNOWN = "unknown"


@dataclass
class PortfolioState:
    """Структурований стан портфеля"""

    # Основні показники
    balance: float = 0.0  # Поточний баланс (за замовчуванням з конфігу, якщо 0)
    position_size: float = 0.0  # Розмір позиції (може бути від'ємним для короткої)
    position_value: float = 0.0  # Вартість позиції
    available_balance: float = 0.0  # Доступний баланс (з конфігу, якщо 0)
    portfolio_value: float = 0.0  # Загальна вартість портфеля (з конфігу, якщо 0)

    # PnL метрики
    unrealized_pnl: float = 0.0  # Нереалізований прибуток/збиток
    realized_pnl: float = 0.0  # Реалізований прибуток/збиток
    total_pnl: float = 0.0  # Загальний PnL

    # Ризик-метрики
    margin_ratio: float = 0.0  # Коефіцієнт маржі
    leverage: float = 1.0  # Плече
    drawdown: float = 0.0  # Поточна просадка
    max_drawdown: float = 0.0  # Максимальна просадка

    # Часові метрики
    time_in_position: int = 0  # Час у позиції (кроки)
    last_trade_timestamp: Optional[datetime] = None

    # Додаткові показники
    entry_price: float = 0.0  # Ціна входу в позицію
    stop_loss: Optional[float] = None  # Стоп-лосс
    take_profit: Optional[float] = None  # Тейк-профіт

    def __post_init__(self):
        """Валідація та нормалізація даних портфеля"""
        # Заповнення значень із конфігу, якщо не задані (0 або None вважаємо відсутністю)
        if not isinstance(self.balance, (int, float)):
            self.balance = 0.0
        if self.balance < 0:
            self.balance = 0.0
        elif self.balance == 0:
            cfg_balance = get_config_with_fallback("trading.initial_cash", fallback=None)
            self.balance = (
                float(cfg_balance)
                if cfg_balance is not None
                else float(self.portfolio_value or 0.0)
            )

        if not isinstance(self.portfolio_value, (int, float)) or self.portfolio_value <= 0:
            cfg_portfolio_value = get_config_with_fallback(
                "trading.defaults.portfolio_value", fallback=None
            )
            self.portfolio_value = (
                float(cfg_portfolio_value)
                if cfg_portfolio_value is not None
                else max(self.balance, 1.0)
            )

        if not isinstance(self.available_balance, (int, float)) or self.available_balance <= 0:
            self.available_balance = 0.0
        if self.available_balance < 0:
            self.available_balance = 0.0
        elif self.available_balance == 0:
            cfg_available = get_config_with_fallback(
                "trading.defaults.available_balance", fallback=None
            )
            self.available_balance = (
                float(cfg_available) if cfg_available is not None else float(self.balance)
            )

        # Базова валідація
        if self.balance < 0:
            logger.warning(f"Negative balance detected: {self.balance}, setting to 0")
            self.balance = 0.0

        if self.portfolio_value <= 0:
            logger.warning(f"Invalid portfolio value: {self.portfolio_value}, setting to balance")
            self.portfolio_value = max(self.balance, 1.0)

        # Розрахунок total_pnl якщо не задано
        if self.total_pnl == 0.0:
            self.total_pnl = self.realized_pnl + self.unrealized_pnl

    def get_portfolio_health(self) -> float:
        """Розрахунок загального здоров'я портфеля (0-1)"""
        try:
            # Базовий рівень для нормалізації беремо з конфігу (без хардкоду)
            cfg_base = get_config_with_fallback("trading.defaults.portfolio_value", fallback=None)
            if cfg_base is None:
                cfg_base = get_config_with_fallback("trading.initial_cash", fallback=None)
            base_level = (
                float(cfg_base)
                if cfg_base is not None
                else max(self.portfolio_value, self.balance, 1.0)
            )
            # Компоненти здоров'я
            balance_health = min(1.0, self.balance / float(base_level)) if self.balance > 0 else 0.0
            pnl_health = max(0.0, min(1.0, (self.total_pnl + 100) / 200))  # Normalized PnL
            drawdown_health = max(0.0, 1.0 - abs(self.drawdown))

            # Композитна оцінка
            health = balance_health * 0.4 + pnl_health * 0.4 + drawdown_health * 0.2
            return float(np.clip(health, 0.0, 1.0))
        except Exception as e:
            logger.warning(f"Error calculating portfolio health: {e}")
            return 0.5  # Neutral fallback


@dataclass
class MarketState:
    """Структурований стан ринку"""

    # Базові ціни
    current_price: float = 100.0
    open_price: float = 100.0
    high_price: float = 100.0
    low_price: float = 100.0
    close_price: float = 100.0

    # Об'єм та ліквідність
    volume: float = 1000.0
    volume_24h: float = 24000.0
    liquidity_depth: float = 100000.0

    # Волатильність та ризик
    volatility: float = 0.02
    volatility_24h: float = 0.025
    beta: float = 1.0

    # Ринкові індикатори
    rsi: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    bb_upper: float = 105.0
    bb_lower: float = 95.0
    sma_10: float = 100.0
    sma_50: float = 100.0

    # Контекст ринку
    market_regime: MarketRegime = MarketRegime.NORMAL
    trend_strength: float = 0.0
    market_sentiment: float = 0.0  # -1 to 1

    # Часові мітки
    timestamp: Optional[datetime] = None
    market_hours: bool = True

    def __post_init__(self):
        """Валідація ринкових даних"""
        # Валідація цін
        if self.current_price <= 0:
            logger.warning(f"Invalid current_price: {self.current_price}, setting to 100.0")
            self.current_price = 100.0

        if self.volume < 0:
            logger.warning(f"Negative volume: {self.volume}, setting to 0")
            self.volume = 0.0

        # Нормалізація індикаторів
        self.rsi = np.clip(self.rsi, 0.0, 100.0)
        self.volatility = max(0.0, self.volatility)
        self.market_sentiment = np.clip(self.market_sentiment, -1.0, 1.0)

    def get_price_change(self) -> float:
        """Розрахунок зміни ціни відносно відкриття"""
        if self.open_price > 0:
            return (self.current_price - self.open_price) / self.open_price
        return 0.0

    def get_volatility_regime(self) -> str:
        """Визначення режиму волатільності"""
        if self.volatility < 0.01:
            return "low"
        elif self.volatility < 0.03:
            return "normal"
        elif self.volatility < 0.05:
            return "high"
        else:
            return "extreme"


@dataclass
class ActionContext:
    """Контекст дії PPO агента"""

    # Основна дія
    action_type: ActionType = ActionType.HOLD
    action_value: float = 0.0  # Розмір дії (-1 to 1)
    action_size: float = 0.0  # Фактичний розмір у одиницях
    raw_action: Optional[np.ndarray] = None  # Сирі дані від PPO

    # Контекст виконання
    confidence: float = 0.5  # Впевненість у дії (0-1)
    expected_return: float = 0.0  # Очікувана прибутковість
    risk_score: float = 0.5  # Оцінка ризику дії (0-1)

    # Транзакційні витрати
    transaction_cost: float = 0.0
    slippage: float = 0.0
    commission: float = 0.0

    # Часовий контекст
    step: int = 0
    episode: int = 0
    total_steps: int = 0

    def __post_init__(self):
        """Валідація контексту дії"""
        # Нормалізація значень
        self.action_value = np.clip(self.action_value, -1.0, 1.0)
        self.confidence = np.clip(self.confidence, 0.0, 1.0)
        self.risk_score = np.clip(self.risk_score, 0.0, 1.0)

        # Валідація витрат
        self.transaction_cost = max(0.0, self.transaction_cost)
        self.slippage = max(0.0, self.slippage)
        self.commission = max(0.0, self.commission)

    def get_total_cost(self) -> float:
        """Розрахунок загальних витрат на транзакцію"""
        return self.transaction_cost + self.slippage + self.commission

    def is_significant_action(self, threshold: float = 0.01) -> bool:
        """Перевірка чи є дія значущою"""
        return abs(self.action_value) > threshold


@dataclass
class RLXContext:
    """
    Типізований контракт даних від PPO агента до ALYSHA

    Цей клас служить єдиним джерелом істини для всіх даних,
    що передаються від RLX (PPO) до ALYSHA reward engine.
    """

    # Основні компоненти
    portfolio: PortfolioState = field(default_factory=PortfolioState)
    market: MarketState = field(default_factory=MarketState)
    action: ActionContext = field(default_factory=ActionContext)

    # Метадані
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "rlx_ppo"
    version: str = "1.0"

    # Додаткові дані
    features: Optional[np.ndarray] = None  # Додаткові ознаки від PPO
    observation: Optional[np.ndarray] = None  # Поточне спостереження
    previous_reward: float = 0.0  # Попередня винагорода
    episode_step: int = 0  # Крок в епізоді

    # Флаги стану
    is_terminal: bool = False  # Чи є термінальний стан
    is_training: bool = True  # Чи йде тренування
    is_evaluation: bool = False  # Чи йде оцінка

    def __post_init__(self):
        """Валідація та нормалізація RLX контексту"""
        # Валідація timestamp
        if not isinstance(self.timestamp, datetime):
            logger.warning("Invalid timestamp, setting to current time")
            self.timestamp = datetime.now()

        # Валідація масивів
        if self.features is not None:
            self.features = np.asarray(self.features, dtype=np.float32)

        if self.observation is not None:
            self.observation = np.asarray(self.observation, dtype=np.float32)

        # Логічна валідація
        if self.is_training and self.is_evaluation:
            logger.warning("Both training and evaluation flags set, prioritizing training")
            self.is_evaluation = False

    def get_context_summary(self) -> Dict[str, Any]:
        """Створення стислого опису контексту для логування"""
        # Витягуємо базові значення з конфігу для уникнення хардкоду
        base_portfolio = get_config_with_fallback(
            "trading.defaults.portfolio_value", fallback=None
        ) or get_config_with_fallback("trading.initial_cash", fallback=None)
        base_available = get_config_with_fallback(
            "trading.defaults.available_balance", fallback=None
        ) or get_config_with_fallback("trading.initial_cash", fallback=None)

        return {
            "timestamp": self.timestamp.isoformat(),
            "portfolio_value": self.portfolio.portfolio_value,
            "position_size": self.portfolio.position_size,
            "current_price": self.market.current_price,
            "action_type": self.action.action_type.value,
            "action_value": self.action.action_value,
            "market_regime": self.market.market_regime.value,
            "episode_step": self.episode_step,
            "is_terminal": self.is_terminal,
        }

    def validate_completeness(self) -> Tuple[bool, List[str]]:
        """Перевірка повноти даних контексту"""
        issues = []

        # Перевірка критичних полів
        if self.portfolio.portfolio_value <= 0:
            issues.append("Invalid portfolio value")

        if self.market.current_price <= 0:
            issues.append("Invalid market price")

        if not isinstance(self.action.action_type, ActionType):
            issues.append("Invalid action type")

        # Перевірка консистентності
        if abs(self.action.action_value) > 1.0:
            issues.append("Action value out of bounds")

        if self.portfolio.balance < 0:
            issues.append("Negative balance")

        return len(issues) == 0, issues


class RLXToAlyshaConverter:
    """
    Безпечний конвертер RLXContext -> ALYSHA StateData

    Обробляє конвертацію типізованих даних від PPO у внутрішній
    формат ALYSHA з повною валідацією та fallback механізмами.
    """

    def __init__(
        self,
        enable_strict_validation: bool = True,
        enable_fallback: bool = True,
        log_conversions: bool = False,
    ):
        """
        Ініціалізація конвертера

        Args:
            enable_strict_validation: Увімкнути сувору валідацію
            enable_fallback: Увімкнути fallback механізми
            log_conversions: Логувати всі конвертації
        """
        self.enable_strict_validation = enable_strict_validation
        self.enable_fallback = enable_fallback
        self.log_conversions = log_conversions

        # Статистика конвертацій
        self.conversion_stats = {
            "total_conversions": 0,
            "successful_conversions": 0,
            "fallback_used": 0,
            "validation_errors": 0,
            "last_conversion": None,
        }

        self.logger = logging.getLogger(f"{__name__}.RLXToAlyshaConverter")

    def convert(self, rlx_context: RLXContext) -> Dict[str, Any]:
        """
        Головний метод конвертації RLXContext -> StateData

        Args:
            rlx_context: Типізований контекст від PPO

        Returns:
            StateData dictionary для ALYSHA
        """
        self.conversion_stats["total_conversions"] += 1
        self.conversion_stats["last_conversion"] = datetime.now()

        try:
            # Валідація вхідних даних
            if self.enable_strict_validation:
                is_valid, issues = rlx_context.validate_completeness()
                if not is_valid:
                    self.conversion_stats["validation_errors"] += 1
                    self.logger.warning(f"Validation issues: {issues}")
                    if not self.enable_fallback:
                        raise ValueError(f"Validation failed: {issues}")

            # Основна конвертація
            state_data = self._convert_to_state_data(rlx_context)

            # Пост-валідація результату
            self._validate_state_data(state_data)

            self.conversion_stats["successful_conversions"] += 1

            if self.log_conversions:
                self.logger.debug(f"Successful conversion: {rlx_context.get_context_summary()}")

            return state_data

        except Exception as e:
            self.logger.error(f"Conversion error: {e}")

            if self.enable_fallback:
                self.conversion_stats["fallback_used"] += 1
                self.logger.info("Using fallback conversion")
                return self._create_fallback_state_data(rlx_context)
            else:
                raise

    def _convert_to_state_data(self, ctx: RLXContext) -> Dict[str, Any]:
        """Основна логіка конвертації"""

        # Базова структура StateData
        state_data = {
            # Метадані
            "timestamp": ctx.timestamp,
            "source": ctx.source,
            "episode_step": ctx.episode_step,
            "is_terminal": ctx.is_terminal,
            # Портфель
            "portfolio_value": float(ctx.portfolio.portfolio_value),
            "available_balance": float(ctx.portfolio.available_balance),
            "position_size": float(ctx.portfolio.position_size),
            "position_value": float(ctx.portfolio.position_value),
            "unrealized_pnl": float(ctx.portfolio.unrealized_pnl),
            "realized_pnl": float(ctx.portfolio.realized_pnl),
            "total_pnl": float(ctx.portfolio.total_pnl),
            "margin_ratio": float(ctx.portfolio.margin_ratio),
            "drawdown": float(ctx.portfolio.drawdown),
            "max_drawdown": float(ctx.portfolio.max_drawdown),
            "portfolio_health": ctx.portfolio.get_portfolio_health(),
            # Ринок
            "price": float(ctx.market.current_price),
            "open_price": float(ctx.market.open_price),
            "high_price": float(ctx.market.high_price),
            "low_price": float(ctx.market.low_price),
            "close_price": float(ctx.market.close_price),
            "volume": float(ctx.market.volume),
            "volatility": float(ctx.market.volatility),
            "market_regime": ctx.market.market_regime.value,
            "price_change": ctx.market.get_price_change(),
            "volatility_regime": ctx.market.get_volatility_regime(),
            # Технічні індикатори
            "rsi": float(ctx.market.rsi),
            "macd": float(ctx.market.macd),
            "macd_signal": float(ctx.market.macd_signal),
            "bb_upper": float(ctx.market.bb_upper),
            "bb_lower": float(ctx.market.bb_lower),
            "sma_10": float(ctx.market.sma_10),
            "sma_50": float(ctx.market.sma_50),
            # Дія
            "action_type": ctx.action.action_type.value,
            "action_value": float(ctx.action.action_value),
            "action_size": float(ctx.action.action_size),
            "action_confidence": float(ctx.action.confidence),
            "action_risk_score": float(ctx.action.risk_score),
            "transaction_cost": float(ctx.action.transaction_cost),
            "slippage": float(ctx.action.slippage),
            "commission": float(ctx.action.commission),
            "total_cost": ctx.action.get_total_cost(),
            "is_significant_action": ctx.action.is_significant_action(),
            # Контекст тренування
            "is_training": ctx.is_training,
            "is_evaluation": ctx.is_evaluation,
            "previous_reward": float(ctx.previous_reward),
            "step": ctx.action.step,
            "episode": ctx.action.episode,
            "total_steps": ctx.action.total_steps,
        }

        # Додаткові дані (опціонально)
        if ctx.features is not None:
            state_data["features"] = (
                ctx.features.tolist() if hasattr(ctx.features, "tolist") else list(ctx.features)
            )

        if ctx.observation is not None:
            state_data["observation"] = (
                ctx.observation.tolist()
                if hasattr(ctx.observation, "tolist")
                else list(ctx.observation)
            )

        # Розрахункові поля для ALYSHA
        state_data.update(self._calculate_derived_fields(ctx))

        return state_data

    def _calculate_derived_fields(self, ctx: RLXContext) -> Dict[str, Any]:
        """Розрахунок похідних полів для ALYSHA"""
        try:
            derived = {}

            # Ефективність портфеля
            if ctx.portfolio.portfolio_value > 0:
                derived["portfolio_return"] = (
                    ctx.portfolio.total_pnl / ctx.portfolio.portfolio_value
                ) * 100
            else:
                derived["portfolio_return"] = 0.0

            # Ризик-метрики
            derived["risk_level"] = self._calculate_risk_level(ctx)
            derived["leverage_ratio"] = abs(ctx.portfolio.position_value) / max(
                ctx.portfolio.available_balance, 1.0
            )

            # Ринкові сигнали
            derived["trend_signal"] = self._calculate_trend_signal(ctx.market)
            derived["momentum_score"] = self._calculate_momentum_score(ctx.market)

            # Якість дії
            derived["action_quality"] = self._calculate_action_quality(ctx)

            return derived

        except Exception as e:
            self.logger.warning(f"Error calculating derived fields: {e}")
            return {}

    def _calculate_risk_level(self, ctx: RLXContext) -> float:
        """Розрахунок загального рівня ризику (0-1)"""
        try:
            # Компоненти ризику
            volatility_risk = min(1.0, ctx.market.volatility / 0.1)  # Нормалізація до 10%
            leverage_risk = min(
                1.0, abs(ctx.portfolio.position_value) / max(ctx.portfolio.portfolio_value, 1.0)
            )
            drawdown_risk = min(1.0, abs(ctx.portfolio.drawdown))
            action_risk = ctx.action.risk_score

            # Композитний ризик
            composite_risk = (
                volatility_risk * 0.3
                + leverage_risk * 0.3
                + drawdown_risk * 0.2
                + action_risk * 0.2
            )

            return float(np.clip(composite_risk, 0.0, 1.0))

        except Exception:
            return 0.5  # Neutral fallback

    def _calculate_trend_signal(self, market: MarketState) -> float:
        """Розрахунок сигналу тренду (-1 to 1)"""
        try:
            # Простий тренд на основі SMA
            if market.sma_10 > market.sma_50:
                sma_signal = 1.0
            elif market.sma_10 < market.sma_50:
                sma_signal = -1.0
            else:
                sma_signal = 0.0

            # RSI тренд
            if market.rsi > 70:
                rsi_signal = -0.5  # Перекупленість
            elif market.rsi < 30:
                rsi_signal = 0.5  # Перепроданість
            else:
                rsi_signal = 0.0

            # MACD тренд
            macd_signal = 1.0 if market.macd > market.macd_signal else -1.0

            # Композитний сигнал
            trend_signal = sma_signal * 0.5 + rsi_signal * 0.3 + macd_signal * 0.2

            return float(np.clip(trend_signal, -1.0, 1.0))

        except Exception:
            return 0.0

    def _calculate_momentum_score(self, market: MarketState) -> float:
        """Розрахунок моментуму (0-1)"""
        try:
            price_momentum = abs(market.get_price_change()) * 10  # Масштабування
            volume_momentum = min(1.0, market.volume / max(market.volume_24h / 24, 1.0))
            volatility_momentum = min(1.0, market.volatility / 0.05)

            momentum = price_momentum * 0.4 + volume_momentum * 0.3 + volatility_momentum * 0.3

            return float(np.clip(momentum, 0.0, 1.0))

        except Exception:
            return 0.0

    def _calculate_action_quality(self, ctx: RLXContext) -> float:
        """Оцінка якості дії (0-1)"""
        try:
            # Факторы качества
            confidence_factor = ctx.action.confidence

            # Відповідність дії ринковим умовам
            trend_signal = self._calculate_trend_signal(ctx.market)
            if ctx.action.action_type == ActionType.BUY and trend_signal > 0:
                trend_alignment = 1.0
            elif ctx.action.action_type == ActionType.SELL and trend_signal < 0:
                trend_alignment = 1.0
            elif ctx.action.action_type == ActionType.HOLD:
                trend_alignment = 0.8  # Нейтральна якість для утримання
            else:
                trend_alignment = 0.3  # Низька якість при протитенденційних діях

            # Розмір дії відносно ризику
            if ctx.action.risk_score > 0.7 and abs(ctx.action.action_value) > 0.5:
                size_appropriateness = 0.3  # Велика дія при високому ризику
            elif ctx.action.risk_score < 0.3 and abs(ctx.action.action_value) < 0.1:
                size_appropriateness = 0.7  # Мала дія при низькому ризику
            else:
                size_appropriateness = 1.0  # Адекватний розмір

            # Композитна якість
            quality = confidence_factor * 0.4 + trend_alignment * 0.4 + size_appropriateness * 0.2

            return float(np.clip(quality, 0.0, 1.0))

        except Exception:
            return 0.5

    def _validate_state_data(self, state_data: Dict[str, Any]) -> None:
        """Валідація створеного StateData"""
        required_fields = ["portfolio_value", "price", "action_type", "timestamp"]

        for field in required_fields:
            if field not in state_data:
                raise ValueError(f"Missing required field: {field}")

        # Валідація типів та діапазонів
        if (
            not isinstance(state_data["portfolio_value"], (int, float))
            or state_data["portfolio_value"] <= 0
        ):
            raise ValueError("Invalid portfolio_value")

        if not isinstance(state_data["price"], (int, float)) or state_data["price"] <= 0:
            raise ValueError("Invalid price")

    def _create_fallback_state_data(self, ctx: RLXContext) -> Dict[str, Any]:
        """Створення мінімально безпечного StateData при збоях"""
        self.logger.warning("Creating fallback StateData")

        # Базові значення з конфігу без хардкоду
        cfg_portfolio = get_config_with_fallback("trading.defaults.portfolio_value", fallback=None)
        cfg_cash = get_config_with_fallback("trading.initial_cash", fallback=None)
        base_portfolio = (
            float(cfg_portfolio) if cfg_portfolio is not None else float(cfg_cash or 0.0)
        )
        cfg_available = get_config_with_fallback(
            "trading.defaults.available_balance", fallback=None
        )
        base_available = (
            float(cfg_available) if cfg_available is not None else float(cfg_cash or base_portfolio)
        )

        price = getattr(ctx.market, "current_price", 100.0) if hasattr(ctx, "market") else 100.0

        return {
            # Мінімальні обов'язкові поля
            "timestamp": datetime.now(),
            "source": "rlx_fallback",
            "episode_step": getattr(ctx, "episode_step", 0),
            "is_terminal": getattr(ctx, "is_terminal", False),
            # Безпечні значення портфеля
            "portfolio_value": (
                float(getattr(ctx.portfolio, "portfolio_value", base_portfolio))
                if hasattr(ctx, "portfolio")
                else base_portfolio
            ),
            "available_balance": (
                float(getattr(ctx.portfolio, "available_balance", base_available))
                if hasattr(ctx, "portfolio")
                else base_available
            ),
            "position_size": (
                float(getattr(ctx.portfolio, "position_size", 0.0))
                if hasattr(ctx, "portfolio")
                else 0.0
            ),
            "position_value": (
                float(getattr(ctx.portfolio, "position_value", 0.0))
                if hasattr(ctx, "portfolio")
                else 0.0
            ),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "margin_ratio": 0.0,
            "drawdown": 0.0,
            "max_drawdown": 0.0,
            "portfolio_health": 0.5,
            # Безпечні значення ринку
            "price": float(price),
            "open_price": 100.0,
            "high_price": 100.0,
            "low_price": 100.0,
            "close_price": 100.0,
            "volume": 1000.0,
            "volatility": 0.02,
            "market_regime": MarketRegime.UNKNOWN.value,
            "price_change": 0.0,
            "volatility_regime": "normal",
            # Технічні індикатори (нейтральні)
            "rsi": 50.0,
            "macd": 0.0,
            "macd_signal": 0.0,
            "bb_upper": 105.0,
            "bb_lower": 95.0,
            "sma_10": 100.0,
            "sma_50": 100.0,
            # Дія (безпечна)
            "action_type": ActionType.HOLD.value,
            "action_value": 0.0,
            "action_size": 0.0,
            "action_confidence": 0.5,
            "action_risk_score": 0.5,
            "transaction_cost": 0.0,
            "slippage": 0.0,
            "commission": 0.0,
            "total_cost": 0.0,
            "is_significant_action": False,
            # Контекст
            "is_training": True,
            "is_evaluation": False,
            "previous_reward": 0.0,
            "step": 0,
            "episode": 0,
            "total_steps": 0,
            # Похідні поля (безпечні значення)
            "portfolio_return": 0.0,
            "risk_level": 0.5,
            "leverage_ratio": 0.0,
            "trend_signal": 0.0,
            "momentum_score": 0.0,
            "action_quality": 0.5,
            # Мітка fallback
            "is_fallback": True,
            "fallback_reason": "conversion_error",
        }

    def get_conversion_stats(self) -> Dict[str, Any]:
        """Отримання статистики конвертацій"""
        stats = self.conversion_stats.copy()

        if stats["total_conversions"] > 0:
            stats["success_rate"] = stats["successful_conversions"] / stats["total_conversions"]
            stats["fallback_rate"] = stats["fallback_used"] / stats["total_conversions"]
            stats["error_rate"] = stats["validation_errors"] / stats["total_conversions"]
        else:
            stats["success_rate"] = 0.0
            stats["fallback_rate"] = 0.0
            stats["error_rate"] = 0.0

        return stats

    def reset_stats(self) -> None:
        """Скидання статистики"""
        self.conversion_stats = {
            "total_conversions": 0,
            "successful_conversions": 0,
            "fallback_used": 0,
            "validation_errors": 0,
            "last_conversion": None,
        }


def create_sample_rlx_context() -> RLXContext:
    """Створення зразкового RLX контексту для тестування"""
    portfolio = PortfolioState(
        balance=950.0,
        position_size=0.1,
        position_value=105.0,
        available_balance=845.0,
        portfolio_value=1055.0,
        unrealized_pnl=5.0,
        realized_pnl=50.0,
        total_pnl=55.0,
        margin_ratio=0.1,
        drawdown=0.02,
        max_drawdown=0.05,
        time_in_position=10,
    )

    market = MarketState(
        current_price=105.0,
        open_price=100.0,
        high_price=107.0,
        low_price=98.0,
        close_price=104.0,
        volume=5000.0,
        volatility=0.025,
        rsi=65.0,
        macd=1.2,
        macd_signal=0.8,
        bb_upper=110.0,
        bb_lower=90.0,
        sma_10=103.0,
        sma_50=101.0,
        market_regime=MarketRegime.BULL,
        trend_strength=0.7,
    )

    action = ActionContext(
        action_type=ActionType.BUY,
        action_value=0.3,
        action_size=0.03,
        confidence=0.75,
        risk_score=0.4,
        transaction_cost=0.1,
        slippage=0.05,
        commission=0.2,
        step=150,
        episode=5,
    )

    return RLXContext(
        portfolio=portfolio,
        market=market,
        action=action,
        episode_step=150,
        previous_reward=2.3,
        is_training=True,
    )


# Утилітарні функції для легкого використання
def convert_rlx_to_alysha(
    rlx_context: RLXContext, strict_validation: bool = True, enable_fallback: bool = True
) -> Dict[str, Any]:
    """
    Зручна функція для швидкої конвертації

    Args:
        rlx_context: Контекст від PPO
        strict_validation: Увімкнути сувору валідацію
        enable_fallback: Увімкнути fallback при помилках

    Returns:
        StateData для ALYSHA
    """
    converter = RLXToAlyshaConverter(
        enable_strict_validation=strict_validation,
        enable_fallback=enable_fallback,
        log_conversions=False,
    )
    return converter.convert(rlx_context)


def validate_rlx_context(rlx_context: RLXContext) -> Tuple[bool, List[str]]:
    """Швидка валідація RLX контексту"""
    return rlx_context.validate_completeness()
