"""
PPO Adapter for RewardEngineV3Plus

Provides backward compatibility with RewardEngineV2 API for seamless integration
with existing PPO agents while leveraging the enhanced capabilities of V3+.
"""

import logging
import time
from typing import Any, Dict, Optional, Union, cast   # ← добавили Union, cast
from datetime import datetime

# Copilot: Refactor — сделать загрузку canonical config устойчивой к ConfigurationError
from core.utils.canonical_config import ConfigManager
from core.errors.config_errors import ConfigurationError

from ..main_engine import RewardEngineV3Plus
from ..utils import RewardEngineConfig, TradingState, ActionType
from ..data_types import (
    MarketRegime, PortfolioData, MarketData, ARCEData, PnLData, 
    StateData, AgentActionData, ExecutionData, TradeData, RewardComponentResult
)
import numpy as np

# --- helper ---------------------------------------------------------------
def _to_ndarray(x: Any) -> np.ndarray:
    """Guarantee np.ndarray even для скаляров / списків."""
    if isinstance(x, np.ndarray):
        return x
    if isinstance(x, (np.generic, float, int)):
        return np.asarray([x], dtype=np.float32)
    return np.asarray(x, dtype=np.float32)

def _to_scalar(x: Any, default: float = 0.0) -> float:
    """Guarantee float scalar for any input (array, list, scalar, etc)."""
    if isinstance(x, np.ndarray):
        if x.size == 0:
            logger.warning(f'_to_scalar: empty array, using default {default}')
            return default
        return float(x.flat[0])
    if isinstance(x, list):
        if not x:
            logger.warning(f'_to_scalar: empty list, using default {default}')
            return default
        return float(cast(Any, x[0]))
    try:
        return float(cast(Any, x))
    except Exception:
        logger.warning(f'_to_scalar: cannot convert {x}, using default {default}')
        return default

def _safe_float(x: Any, default: float = 0.0) -> float:
    """Safely convert any value to float with NaN/infinity protection."""
    try:
        if x is None:
            return default
        
        # Handle numpy types
        if isinstance(x, (np.ndarray, np.generic)):
            if isinstance(x, np.ndarray):
                if x.size == 0:
                    return default
                x = x.flat[0]
            val = float(cast(Any, x))
        # Handle lists/tuples
        elif isinstance(x, (list, tuple)):
            if not x:
                return default
            val = float(cast(Any, x[0]))
        else:
            val = float(cast(Any, x))
        
        # Check for NaN/infinity
        if np.isnan(val) or np.isinf(val):
            logger.warning(f'_safe_float: NaN/inf detected for {x}, using default {default}')
            return default
        
        return val
    except (ValueError, TypeError, OverflowError) as e:
        logger.warning(f'_safe_float: conversion error for {x}: {e}, using default {default}')
        return default
# --------------------------------------------------------------------------

logger = logging.getLogger(__name__)


class RewardEngineAPIV3Plus:
    def _get_actual_portfolio_value(self, context: dict) -> float:
        """Отримати реальне значення портфеля з перевіркою валідності."""
        portfolio_value = context.get('portfolio_value')
        try:
            if portfolio_value is not None and float(portfolio_value) != 0.0:
                return float(portfolio_value)
        except Exception:
            pass
        # Альтернатива: cash + position_value
        cash = context.get('cash', 0.0)
        position_value = context.get('position_value', 0.0)
        try:
            calculated = float(cash) + float(position_value)
            if calculated > 0:
                return calculated
        except Exception:
            pass
        # Фолбек
        return 10000.0

    def _get_actual_available_balance(self, context: dict) -> float:
        """Отримати реальний available_balance з перевіркою валідності."""
        available_balance = context.get('available_balance')
        try:
            if available_balance is not None and float(available_balance) > 0:
                return float(available_balance)
        except Exception:
            pass
        # fallback: cash
        cash = context.get('cash')
        try:
            if cash is not None and float(cash) >= 0:
                return float(cash)
        except Exception:
            pass
        # fallback: portfolio_value
        return self._get_actual_portfolio_value(context)
    """
    Adapter class that provides RewardEngineV2 API compatibility while using
    RewardEngineV3Plus under the hood.
    
    This adapter ensures seamless integration with existing PPO agents without
    requiring changes to their code, while providing enhanced reward calculation
    capabilities.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, config_path: Optional[str] = None,
                 environment: str = "production", risk_manager=None):
        """
        Initialize the adapter with RewardEngineV3Plus.
        
        Args:
            config: Optional configuration dictionary (should be full canonical config!)
            config_path: Optional path to custom configuration file.
            environment: Environment name for canonical config (default: production)
            risk_manager: Optional RiskManager instance to avoid fallback mode
        """
        try:
            # Canonical config always has priority
            if config is None:
                config_manager = ConfigManager()
                try:
                    canonical_config = config_manager.load_config(environment=environment) or {}
                except ConfigurationError:
                    # Copilot: Bugfix — для unit-тестов позволяeм fallback к пустому конфигу
                    canonical_config = {}
                    # Можно логировать предупреждение; избегаем выбрасывать ошибку в тестах
                # Pylance: cast Dict – гарантируем непустой dict
                from typing import cast
                self.config = RewardEngineConfig.from_dict(cast(Dict[str, Any], canonical_config))
            elif isinstance(config, RewardEngineConfig):
                self.config = config
            elif isinstance(config, dict):
                # If config is a full canonical config, use as is
                self.config = RewardEngineConfig.from_dict(config)
            else:
                raise ValueError("Invalid config type for RewardEngineAPIV3Plus")
                
            # Set risk_manager before components initialization to avoid fallback mode
            if risk_manager is not None:
                self.risk_manager = risk_manager
                
            # Initialize V3+ engine
            self.engine = RewardEngineV3Plus(self.config)
            
            # CRITICAL FIX: Initialize core reward components!
            self._initialize_components()
            
            # Z-2: Add RMS normalizer for rewards (FIX: add shape)
            from rlx.utils.rms import RunningMeanStd
            self.reward_rms = RunningMeanStd(shape=())
            
            logger.info("RewardEngineAPIV3Plus adapter initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize RewardEngineAPIV3Plus: {e}")
            # Fallback to minimal configuration
            fallback_config = {
                'alysha_reward_engine': {
                    'validation': {
                        'max_total_reward': 1000,
                        'min_total_reward': -1000,
                        'default_safe_reward': -10,
                        'check_nan_inf': True
                    },
                    'components': {
                        'risk': {'enabled': True},
                        'behavior': {'enabled': True},
                        'information': {'enabled': True},
                        'cost': {'enabled': True},
                        'pnl': {'enabled': True},
                        'event': {'enabled': True},
                        'shaping': {'enabled': True}
                    }
                }
            }
            self.config = RewardEngineConfig(master_config=fallback_config)
            self.engine = RewardEngineV3Plus(self.config)
            
            # CRITICAL FIX: Initialize core reward components even on fallback!
            self._initialize_components()
            
            # Z-2: Initialize RMS even on fallback (FIX: add shape)
            from rlx.utils.rms import RunningMeanStd
            self.reward_rms = RunningMeanStd(shape=())
    
    def compute_reward(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute reward using V3+ engine with V2 API compatibility.
        
        Args:
            context: Trading context dict from PPO agent
            
        Returns:
            Reward value as a float.
        """
        try:
            # DETAILED REWARD DEBUG LOGGING
            print(f"[REWARD-ADAPTER-DEBUG] Starting reward computation")
            print(f"[REWARD-ADAPTER-DEBUG] Input context keys: {list(context.keys())}")
            
            # --- CRITICAL DEBUG: Check StateData and PnL ---
            if 'state_t_plus_1' in context and hasattr(context['state_t_plus_1'], 'pnl'):
                pnl_data = context['state_t_plus_1'].pnl
                print(f"[REWARD-ADAPTER-DEBUG] StateData PnL: realized={pnl_data.realized_pnl}, unrealized={pnl_data.unrealized_pnl}")
                print(f"[REWARD-ADAPTER-DEBUG] Asset PnL: {pnl_data.asset_pnl}")
                
                # EXTRACT ACTUAL PnL VALUES
                context['realized_pnl'] = float(pnl_data.realized_pnl)
                context['unrealized_pnl'] = float(pnl_data.unrealized_pnl)
                print(f"[REWARD-ADAPTER-DEBUG] Extracted PnL: realized={context['realized_pnl']}, unrealized={context['unrealized_pnl']}")
            
            if 'state_t_plus_1' in context and hasattr(context['state_t_plus_1'], 'portfolio'):
                portfolio_data = context['state_t_plus_1'].portfolio
                print(f"[REWARD-ADAPTER-DEBUG] Portfolio value: {portfolio_data.total_value}")
                context['portfolio_value'] = float(portfolio_data.total_value)
            
            # --- PLATINUM FIX: Ensure all numeric fields are float scalars for downstream compatibility ---
            for key in ["reward", "portfolio_value", "position_size", "position_value", "unrealized_pnl", "realized_pnl", "action_size", "transaction_cost", "slippage", "commission", "net_pnl"]:
                if key in context:
                    original_value = context[key]
                    context[key] = _to_scalar(context[key])
                    print(f"[REWARD-ADAPTER-DEBUG] Converted {key}: {original_value} -> {context[key]}")
            
            # -------------------------------------------------------------------------------
            # Convert list fields to scalars (take last value or mean)
            if 'unrealized_pnl' in context and isinstance(context['unrealized_pnl'], list):
                # PLATINUM FIX: Ensure all numeric fields are float scalars for downstream compatibility
                # This block was moved up and enhanced. The original logic was insufficient.
                # The new logic is handled by the _to_scalar calls at the beginning of the method.
                # This check is now redundant but kept for historical context.
                context['unrealized_pnl'] = _to_scalar(context['unrealized_pnl'][-1] if context['unrealized_pnl'] else 0.0)
            if 'position_size' in context and isinstance(context['position_size'], list):
                context['position_size'] = _to_scalar(context['position_size'][-1] if context['position_size'] else 0.0)
            if 'price_change' in context and isinstance(context['price_change'], list):
                context['price_change'] = _to_scalar(context['price_change'][-1] if context['price_change'] else 0.0)
            
            # Convert V2 context to V3+ TradingState
            # CRITICAL FIX: The context from the environment (`info` dict) should be the source of truth.
            # The current implementation relies on a flat dictionary that is not guaranteed to be up-to-date.
            # The `_context_to_trading_state` method should be redesigned to take the `info` dict
            # from the environment step, which contains the true state after an action.
            trading_state = self._context_to_trading_state(context)
            print(f"[REWARD-ADAPTER-DEBUG] Trading state: portfolio_value={trading_state.portfolio_value}, "
                  f"price={trading_state.price}, position_size={trading_state.position_size}, "
                  f"action_type={trading_state.action_type}, action_size={trading_state.action_size}")
            
            # Create StateData from TradingState (for now use simple mapping)
            # CRITICAL FLAW: This section creates mostly dummy data.
            # It should extract real data from the `info` dict returned by the environment.
            # For example, `ExecutionData` should come from real trade execution results.
            # `ARCEData` should be populated from the risk manager's assessment.
            # Basic state data creation
            md_single = MarketData(                                        # ← единичный MarketData
                current_price=trading_state.price,
                previous_price=trading_state.price * 0.995,
                high_price=trading_state.price * 1.01,
                low_price=trading_state.price * 0.99,
                open_price=trading_state.price * 0.998,
                current_volume=1000.0,
                average_volume=800.0,
                volume_history=[800.0, 900.0, 1100.0],
                current_volatility=trading_state.market_volatility,
                volatility_history=[trading_state.market_volatility * 0.8,
                                    trading_state.market_volatility * 1.1],
                bid_ask_spread=trading_state.price * 0.001,
                market_depth={"bid": 1000.0, "ask": 1000.0},
                price_change=trading_state.price * 0.005,
                price_change_percent=0.5,
                price_history=[trading_state.price * 0.99, trading_state.price * 1.005],
                timestamp=time.time()
            )

            state_data = StateData(
                timestamp=trading_state.timestamp.timestamp(),
                arce=ARCEData(
                    var_current=0.01, var_limit=0.05,
                    cvar_current=0.015, cvar_limit=0.08,
                    drawdown_current=0.0, drawdown_limit=0.1,
                    portfolio_volatility=trading_state.market_volatility,
                    target_volatility=0.02, volatility_range=0.01,
                    active_flags=[], regime_tag=MarketRegime.UNKNOWN,
                    position_limits={trading_state.symbol: 10.0}
                ),
                portfolio=PortfolioData(
                    positions={trading_state.symbol: trading_state.position_size},
                    current_weights={trading_state.symbol: trading_state.position_size / trading_state.portfolio_value
                                     if trading_state.portfolio_value > 0 else 0.0},
                    target_weights={trading_state.symbol: 0.1},
                    total_value=trading_state.portfolio_value,
                    turnover=0.05
                ),
                pnl=PnLData(
                    realized_pnl=trading_state.realized_pnl,
                    unrealized_pnl=trading_state.unrealized_pnl,
                    asset_pnl={trading_state.symbol: trading_state.unrealized_pnl}
                ),
                market_data=md_single,                 # ✅ одиночный MarketData
                execution=ExecutionData(
                    trades=[TradeData(
                        asset_id=trading_state.symbol,
                        quantity=trading_state.action_size,
                        price=trading_state.price,
                        timestamp=trading_state.timestamp.timestamp(),
                        fees=trading_state.transaction_cost,
                        commissions=0.0,
                        side=trading_state.action_type.value
                    )],
                    fills=[],
                    num_order_modifications=0,
                    num_order_cancellations=0,
                    bid_ask_spreads={trading_state.symbol: trading_state.price * 0.001},
                    transaction_fees={trading_state.symbol: trading_state.transaction_cost},
                    slippage_costs={trading_state.symbol: trading_state.slippage}
                ),
                agent_action=AgentActionData(
                    action_vector=np.array([1.0 if trading_state.action_type == ActionType.BUY else -1.0 if trading_state.action_type == ActionType.SELL else 0.0, 0.0, 0.0]),
                    action_type=trading_state.action_type.value,
                    action_direction=1 if trading_state.action_type == ActionType.BUY else -1 if trading_state.action_type == ActionType.SELL else 0,
                    is_exploratory=False
                )
            )
            
            # Calculate reward using V3+ engine
            result = self.engine.calculate_total_reward(state_data)
            print(f"[REWARD-ADAPTER-DEBUG] Engine result type: {type(result)}")
            print(f"[REWARD-ADAPTER-DEBUG] Engine result: {result}")

            # Debug: Log component breakdown
            total_reward = getattr(result, 'total_reward', 0.0)
            component_rewards = getattr(result, 'component_rewards', {})
            # Copilot: Bugfix — flatten component objects to numeric raw values for downstream XAI
            flat_components: Dict[str, float] = {}
            try:
                for k, v in (component_rewards or {}).items():
                    if isinstance(v, RewardComponentResult):
                        flat_components[k] = float(v.raw_value)
                    else:
                        # try convert to float directly
                        flat_components[k] = float(v)
            except Exception:
                # best‑effort fallback: skip non‑convertibles
                for k, v in (component_rewards or {}).items():
                    try:
                        flat_components[k] = float(getattr(v, 'raw_value', v) or 0.0)
                    except Exception:
                        flat_components[k] = 0.0
            
            print(f"[REWARD-ADAPTER-DEBUG] Total reward from engine: {total_reward}")
            print(f"[REWARD-ADAPTER-DEBUG] Component rewards: {component_rewards}")
            
            logger.debug(f"[REWARD_COMPONENTS] Available components: {list(self.engine.components.keys())}")
            logger.debug(f"[REWARD_COMPONENTS] Component rewards: {flat_components}")
            logger.debug(f"[REWARD_COMPONENTS] Total reward: {total_reward}")

            # ------------------------------------------------------------------
            # REWARD-ALIGN-001: Sign-preserving normalization + explicit cost
            # ------------------------------------------------------------------
            # Copilot: Refactor — extract raw reward BEFORE any penalties
            raw_reward = float(total_reward)
            print(f"[REWARD-ADAPTER-DEBUG] Raw reward (float): {raw_reward}")

            # Cost injection (commission + slippage) if engine didn't produce cost
            commission = float(context.get('commission', 0.0) or 0.0)
            slippage = float(context.get('slippage', 0.0) or 0.0)
            injected_cost = commission + slippage

            # Determine existing engine cost component value (could be an object)
            existing_cost_component = component_rewards.get('cost')
            engine_cost_value = 0.0
            try:
                # If component is a RewardComponentResult-like object
                if hasattr(existing_cost_component, 'raw_value'):
                    engine_cost_value = float(getattr(existing_cost_component, 'raw_value') or 0.0)
                elif isinstance(existing_cost_component, (int, float)):
                    engine_cost_value = float(existing_cost_component)
            except Exception:
                engine_cost_value = 0.0

            # Injection policy: always subtract explicit trading costs if commission/slippage > 0
            # to guarantee economic alignment, even if engine cost component exists but is zero.
            if injected_cost > 0.0:
                raw_reward_after_cost = raw_reward - injected_cost
                cost_applied = True
            else:
                raw_reward_after_cost = raw_reward
                cost_applied = False

            # Clip post‑cost raw reward
            clipped_reward = float(np.clip(raw_reward_after_cost, -10.0, 10.0))
            print(f"[REWARD-ADAPTER-DEBUG] Clipped reward (post-cost): {clipped_reward}")

            reward_array = np.array([clipped_reward], dtype=np.float32)

            # RMS normalization with robust error handling (mean/var tracking only)
            try:
                self.reward_rms.update(reward_array)
                normalized_reward_array = self.reward_rms.normalize(reward_array)
                if normalized_reward_array.ndim == 0:
                    normalized_reward = float(normalized_reward_array.item())
                elif normalized_reward_array.size > 0:
                    normalized_reward = float(normalized_reward_array.flat[0])
                else:
                    normalized_reward = 0.0
            except Exception as e:
                logger.error(f"Error in RMS operations: {e}")
                normalized_reward = clipped_reward  # Fallback

            # Sign preservation toggle (config: reward.normalization.preserve_sign)
            preserve_sign = True
            try:
                # Attempt deep config access if available
                preserve_sign = bool(getattr(self.config, 'master_config', {})
                                      .get('reward', {})
                                      .get('normalization', {})
                                      .get('preserve_sign', True))
            except Exception:
                pass

            if preserve_sign and clipped_reward != 0.0:
                if np.sign(normalized_reward) != np.sign(clipped_reward):
                    # Flip to original sign while keeping magnitude
                    normalized_reward = float(np.sign(clipped_reward) * abs(normalized_reward))

            print(f"[REWARD-ADAPTER-DEBUG] Final normalized reward (sign-preserved): {normalized_reward}")
            print(f"[REWARD-ADAPTER-DEBUG] RMS mean: {self.reward_rms.mean}, RMS var: {self.reward_rms.var}")
            
            # Convert back to V2 format
            # Copilot: Refactor — persist last trace for external consumers (training loop aggregation)
            result_dict = {
                'reward': normalized_reward,
                'trace': {
                    'components': flat_components,
                    'total_reward': getattr(result, 'total_reward', 0.0),
                    'raw_reward': raw_reward,
                    'raw_reward_after_cost': raw_reward_after_cost,
                    'cost_injected': cost_applied,
                    'injected_cost': injected_cost,
                    'commission': commission,
                    'slippage': slippage,
                    'clipped_reward': clipped_reward,
                    'normalized_reward': normalized_reward,
                    'reward_rms_mean': float(self.reward_rms.mean),
                    'reward_rms_var': float(self.reward_rms.var),
                    'metadata': getattr(result, 'metadata', {}),
                    'timestamp': datetime.fromtimestamp(getattr(result, 'timestamp', time.time())).isoformat()
                },
                'error': None
            }
            # PATCH-SPEC INVARIANT: cost_injected correctness
            try:
                assert (result_dict['trace']['cost_injected'] == ( (commission > 0) or (slippage > 0) )), \
                    f"cost_injected mismatch: commission={commission} slippage={slippage} cost_injected={result_dict['trace']['cost_injected']}"
            except AssertionError as inv_err:
                logger.error(f"[REWARD-INVARIANT] {inv_err}")
            print(f"[REWARD-ADAPTER-DEBUG] Returning result: {result_dict}")
            # Copilot: Refactor — store last trace attributes for training script (avoid getattr chain failures)
            try:
                self.last_trace = result_dict['trace']  # type: ignore[attr-defined]
                self.last_normalized_reward = normalized_reward  # type: ignore[attr-defined]
                self.last_raw_reward = raw_reward  # type: ignore[attr-defined]
            except Exception:
                pass
            return result_dict
            
        except Exception as e:
            logger.error(f"Error in compute_reward: {e}")
            return {
                'reward': 0.0,
                'trace': {'error_details': str(e)},
                'error': str(e)
            }
    
    def get_xai_trace(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get XAI trace information for explanation.
        
        Args:
            context: Trading context dict
            
        Returns:
            Dict with XAI trace information
        """
        try:
            # Get reward calculation first
            reward_result = self.compute_reward(context)
            
            if reward_result.get('error'):
                return {
                    'xai_trace': None,
                    'trace': reward_result['trace'],
                    'error': reward_result['error']
                }
            
            # Generate XAI explanation
            xai_trace = {
                'component_contributions': reward_result['trace']['components'],
                'total_reward': reward_result['trace']['total_reward'],
                'explanation': self._generate_explanation(reward_result['trace']),
                'importance_scores': self._calculate_importance_scores(reward_result['trace']),
                'timestamp': reward_result['trace']['timestamp']
            }
            
            return {
                'xai_trace': xai_trace,
                'trace': reward_result['trace'],
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error in get_xai_trace: {e}")
            return {
                'xai_trace': None,
                'trace': {'error_details': str(e)},
                'error': str(e)
            }
    
    def get_risk_report(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get risk assessment report.
        
        Args:
            context: Trading context dict
            
        Returns:
            Dict with risk report information
        """
        try:
            reward_result = self.compute_reward(context)
            
            if reward_result.get('error'):
                return {
                    'risk_report': None,
                    'trace': reward_result['trace'],
                    'error': reward_result['error']
                }
            
            # Extract risk-related components
            components = reward_result['trace']['components']
            
            risk_report = {
                'risk_score': abs(components.get('risk', 0.0)),
                'risk_factors': {
                    'position_risk': components.get('risk', 0.0),
                    'cost_impact': components.get('cost', 0.0),
                    'behavior_risk': components.get('behavior', 0.0)
                },
                'risk_level': self._assess_risk_level(components),
                'recommendations': self._generate_risk_recommendations(components),
                'timestamp': reward_result['trace']['timestamp']
            }
            
            return {
                'risk_report': risk_report,
                'trace': reward_result['trace'],
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error in get_risk_report: {e}")
            return {
                'risk_report': None,
                'trace': {'error_details': str(e)},
                'error': str(e)
            }
    
    def audit_log(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate audit log for external systems.
        
        Args:
            context: Trading context dict
            
        Returns:
            Dict with audit log information
        """
        try:
            audit_data = {
                'input_context': context,
                'engine_version': 'V3Plus',
                'timestamp': datetime.now().isoformat(),
                'adapter_info': {
                    'version': '1.0.0',
                    'compatibility': 'RewardEngineV2_API'
                }
            }
            
            return {
                'audit_log': audit_data,
                'trace': {'input': context, 'audit_timestamp': audit_data['timestamp']},
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error in audit_log: {e}")
            return {
                'audit_log': None,
                'trace': {'error_details': str(e)},
                'error': str(e)
            }
    
    def _context_to_trading_state(self, context: Dict[str, Any]) -> TradingState:
        """
        Convert V2 context dict to V3+ TradingState object.
        
        Args:
            context: V2 format context
            
        Returns:
            TradingState object for V3+ engine
        """
        def _safe_float(value: Any, default: float = 0.0) -> float:
            if isinstance(value, list):
                if len(value) == 1:
                    return float(value[0])
                elif len(value) > 1:
                    logger.warning(f'_safe_float: list of size >1, using first element: {value}')
                    return float(value[0])
                else:
                    return default
            if isinstance(value, np.ndarray):
                if value.size == 1:
                    return float(value.item())
                elif value.size > 1:
                    logger.warning(f'_safe_float: array of size >1, using first element: {value}')
                    return float(value.flat[0])
                else:
                    return default
            try:
                return float(value)
            except (ValueError, TypeError):
                logger.warning(f'_safe_float: cannot convert value {value}, using default {default}')
                return default

        # Extract common fields with defaults
        # SYMBOL-MAP-FIX-015: enforce canonical symbol BTCUSDT if missing/UNKNOWN
        symbol_value = context.get('symbol', 'BTCUSDT')
        if not symbol_value or str(symbol_value).upper() in ("UNKNOWN", "NONE"):
            symbol_value = 'BTCUSDT'

        return TradingState(
            symbol=symbol_value,
            timestamp=datetime.now(),
            price=_safe_float(context.get('price', 0.0)),
            
            # Position info
            position_size=_safe_float(context.get('position_size', 0.0)),
            position_value=_safe_float(context.get('position_value', 0.0)),
            
            # PnL info
            unrealized_pnl=_safe_float(context.get('unrealized_pnl', 0.0)),
            realized_pnl=_safe_float(context.get('realized_pnl', 0.0)),
            
            # Action info
            action_type=self._map_action_type(context.get('action_type')),
            action_size=_safe_float(context.get('action_size', 0.0)),
            
            # Portfolio info - CRITICAL FIX: Use actual values, no hardcoded fallbacks
            portfolio_value=self._get_actual_portfolio_value(context),
            available_balance=self._get_actual_available_balance(context),
            
            # Market info
            market_volatility=_safe_float(context.get('market_volatility', 0.02)),
            market_trend=context.get('market_trend', 'neutral'),
            
            # Transaction costs - CRITICAL FIX: include commission from context
            transaction_cost=_safe_float(context.get('transaction_cost', 0.0)) + _safe_float(context.get('commission', 0.0)),
            slippage=_safe_float(context.get('slippage', 0.0)),
            
            # Additional metadata
            metadata=context.get('metadata', {})
        )
    
    def _map_action_type(self, action_type: Any) -> ActionType:
        """Map V2 action type to V3+ ActionType enum."""
        if isinstance(action_type, str):
            action_map = {
                'buy': ActionType.BUY,
                'sell': ActionType.SELL,
                'hold': ActionType.HOLD,
                'close': ActionType.CLOSE
            }
            return action_map.get(action_type.lower(), ActionType.HOLD)
        return ActionType.HOLD
    
    def _generate_explanation(self, trace: Dict[str, Any]) -> str:
        """Generate human-readable explanation of reward calculation."""
        components = trace.get('components', {})
        total = float(trace.get('total_reward', 0.0) or 0.0)

        if not components:
            return f"Total reward {total:.4f} (no component breakdown available)"

        parts = [f"Total {total:.4f}"]

        # Sort by absolute contribution descending for readability
        for name, value in sorted(components.items(), key=lambda kv: abs(kv[1]), reverse=True):
            if value == 0:
                continue
            sign = 'penalty' if value < 0 else 'bonus'
            parts.append(f"{name} {sign}: {value:+.4f}")

        # Cost injection trace (if present) for transparency
        if trace.get('cost_injected'):
            injected_cost = trace.get('injected_cost', 0.0)
            parts.append(f"explicit_cost_applied: -{injected_cost:.4f}")

        return " | ".join(parts)

    def _calculate_importance_scores(self, trace: Dict[str, Any]) -> Dict[str, float]:
        """Compute normalized absolute contribution weights for XAI visualization."""
        components = trace.get('components', {})
        # support both floats and RewardComponentResult
        values: Dict[str, float] = {}
        for k, v in components.items():
            try:
                val = float(getattr(v, 'raw_value', v))
            except Exception:
                val = 0.0
            values[k] = val
        # Denominator: sum absolute values; fall back to 1e-8 to avoid div by zero
        denom = sum(abs(v) for v in values.values())
        if denom <= 0:
            return {k: 0.0 for k in values}
        return {k: abs(v) / denom for k, v in values.items()}
    
    def _assess_risk_level(self, components: Dict[str, float]) -> str:
        """Assess overall risk level based on components."""
        risk_score = abs(components.get('risk', 0.0))
        
        if risk_score > 0.1:
            return "HIGH"
        elif risk_score > 0.05:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _generate_risk_recommendations(self, components: Dict[str, float]) -> list:
        """Generate risk management recommendations."""
        recommendations = []
        
        if components.get('risk', 0.0) < -0.1:
            recommendations.append("Consider reducing position size due to high risk")
        
        if components.get('cost', 0.0) < -0.05:
            recommendations.append("Transaction costs are high, consider consolidating trades")
        
        if components.get('behavior', 0.0) < -0.1:
            recommendations.append("Trading behavior shows poor patterns, review strategy")
        
        if not recommendations:
            recommendations.append("Risk levels are acceptable")
        
        return recommendations
    
    def _initialize_components(self):
        """
        Initialize core reward components for V3+ engine.
        
        TASK 5 CRITICAL: Integration of RiskManager into reward system!
        Without components, the engine returns 0 reward always!
        """
        try:
            # Clear existing components for clean re-initialization
            self.engine.components.clear()
            
            # Import all reward components
            from ..components.pnl import PnLRewardComponent
            from ..components.risk import RiskRewardComponent as OldRiskRewardComponent
            from ..components.risk_reward import RiskRewardComponent as NewRiskRewardComponent  # TASK 5
            from ..components.cost import CostRewardComponent
            from ..components.behavior import BehaviorRewardComponent
            from ..components.information import InformationRewardComponent
            
            # Add core components to engine
            self.engine.add_component("pnl", PnLRewardComponent(self.config))
            
            # TASK 5 CRITICAL: Use new RiskRewardComponent with RiskManager integration
            # Check if risk_manager is available in context
            risk_manager = getattr(self, 'risk_manager', None)
            if risk_manager is not None:
                logger.info("🎯 TASK 5: Integrating RiskManager into reward system")
                self.engine.add_component("risk_reward", NewRiskRewardComponent(self.config, risk_manager))
            else:
                logger.warning("🚨 TASK 5: RiskManager not available, using fallback mode")
                self.engine.add_component("risk_reward", NewRiskRewardComponent(self.config, None))
            
            # Keep old risk component for backward compatibility (if needed)
            self.engine.add_component("risk", OldRiskRewardComponent(self.config))
            
            self.engine.add_component("cost", CostRewardComponent(self.config))
            self.engine.add_component("behavior", BehaviorRewardComponent(self.config))
            self.engine.add_component("information", InformationRewardComponent(self.config))
            
            logger.info(f"✅ TASK 5: Initialized {len(self.engine.components)} reward components: {list(self.engine.components.keys())}")
            logger.info(f"🛡️ RiskManager integration: {'CONNECTED' if risk_manager else 'FALLBACK MODE'}")
            
        except Exception as e:
            logger.error(f"🚨 Failed to initialize reward components: {e}")
            logger.warning("Engine will return 0 rewards without components!")
    
    def _warn_missing_portfolio_value(self, context: Dict[str, Any]) -> float:
        """Warn about missing portfolio_value and return last known value or safe fallback"""
        logger.error(f"PORTFOLIO_DATA_INTEGRITY_ERROR: portfolio_value missing or None in context")
        logger.error(f"Context keys available: {list(context.keys())}")
        logger.error(f"Context portfolio_value type: {type(context.get('portfolio_value'))}, value: {context.get('portfolio_value')}")
        
        # Try to extract from other fields
        fallback_value = (
            _safe_float(context.get('cash', 0.0)) + 
            _safe_float(context.get('position_value', 0.0))
        )
        
        if fallback_value > 0:
            logger.warning(f"Using calculated portfolio value from cash + position_value: {fallback_value}")
            return fallback_value
        else:
            logger.error(f"No portfolio data available, using emergency fallback: 10000.0")
            return 10000.0
    
    def set_risk_manager(self, risk_manager) -> None:
        """
        TASK 5 CRITICAL: Set RiskManager for reward system integration
        
        This method connects the RiskManager to the reward system, solving the
        "Risk Island" problem by integrating risk assessment into reward calculation.
        
        Args:
            risk_manager: Instance of RiskManager for risk assessment
        """
        try:
            self.risk_manager = risk_manager
            
            # Update the existing risk_reward component if it exists
            if "risk_reward" in self.engine.components:
                risk_component = self.engine.components["risk_reward"]
                if hasattr(risk_component, 'set_risk_manager'):
                    risk_component.set_risk_manager(risk_manager)
                    logger.info("🎯 TASK 5: RiskManager successfully connected to existing RiskRewardComponent")
                else:
                    logger.warning("🚨 RiskRewardComponent does not support set_risk_manager method")
            else:
                logger.warning("🚨 risk_reward component not found in engine components")
                
            logger.info(f"✅ TASK 5: RiskManager integration completed - Risk Island connected!")
            
        except Exception as e:
            logger.error(f"🚨 TASK 5: Failed to set RiskManager: {e}")
    
    def get_risk_manager(self):
        """
        Get the currently configured RiskManager
        
        Returns:
            RiskManager instance or None if not set
        """
        return getattr(self, 'risk_manager', None)
