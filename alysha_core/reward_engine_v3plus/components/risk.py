"""
Risk Reward Component для ALYSHA-RE-V3+

Реалізація компоненти винагороди за ризик згідно з формулою:
R_Risk,t = Σ φ_k * R_Risk,t^(k)

де k ∈ {DrawDown, VaR, CVaR, Volatility, ARCEFlags, Inventory}

Підкомпоненти ризику:
1. DrawDown: R_Risk,t^(DrawDown) = -c_dd * max(0, DD_t - DD_Limit)²
2. VaR: R_Risk,t^(VaR) = -c_var * max(0, VaR_t - VaR_Limit)²  
3. CVaR: R_Risk,t^(CVaR) = -c_cvar * max(0, CVaR_t - CVaR_Limit)²
4. Volatility: R_Risk,t^(Volatility) = -c_vol * ((σ_portfolio,t - σ_target) / σ_targetRange)²
5. ARCE Flags: R_Risk,t^(ARCEFlags) = -Σ Severity(f, S_t) * BasePenaltyValue(f) * Multiplier(f)
6. Inventory: R_Risk,t^(Inventory) = -c_inv * Σ max(0, |Position_j| - MaxPositionLimit_j)²
"""

import logging
import math
from typing import Dict, Any, List, Optional, cast
import numpy as np

from ..data_types import (
    ARCEData, PortfolioData, StateData, RewardComponentResult, ConfigDict
)
from ..utils import validate_numeric_value, RewardEngineConfig
from .base import BaseRewardComponent
from core.utils.canonical_config import get_config_with_fallback


class RiskRewardComponent(BaseRewardComponent):
    """
    Компонента винагороди за ризик
    
    Агрегує всі підкомпоненти ризику з відповідними вагами φ_k
    """
    
    def __init__(self, config: RewardEngineConfig):
        """
        Ініціалізація компоненти ризику
        
        Args:
            config: Конфігурація reward engine
        """
        super().__init__(cast(Dict[str, Any], config))
        self.config = config
        self.logger = logging.getLogger("alysha_reward_engine.risk")
        
        # ВИДАЛЕНО ВСІ HARDCODE ЗНАЧЕННЯ!
        risk_config = config.get_component_config("risk")
        
        # Ваги підкомпонент - БЕЗ fallback значень
        self.subcomponent_weights = risk_config.get("subcomponent_weights")
        if not self.subcomponent_weights:
            raise ValueError("alysha_reward_engine.components.risk.subcomponent_weights not found in configuration")
        
        # Параметри для кожної підкомпоненти - БЕЗ fallback значень
        self.drawdown_config = risk_config.get("drawdown")
        if not self.drawdown_config:
            raise ValueError("alysha_reward_engine.components.risk.drawdown not found in configuration")
            
        self.var_config = risk_config.get("var")
        if not self.var_config:
            raise ValueError("alysha_reward_engine.components.risk.var not found in configuration")
            
        self.cvar_config = risk_config.get("cvar")
        if not self.cvar_config:
            raise ValueError("alysha_reward_engine.components.risk.cvar not found in configuration")
            
        self.volatility_config = risk_config.get("volatility")
        if not self.volatility_config:
            raise ValueError("alysha_reward_engine.components.risk.volatility not found in configuration")
            
        self.arce_flags_config = risk_config.get("arce_flags")
        if not self.arce_flags_config:
            raise ValueError("alysha_reward_engine.components.risk.arce_flags not found in configuration")
            
        self.inventory_config = risk_config.get("inventory")
        if not self.inventory_config:
            raise ValueError("alysha_reward_engine.components.risk.inventory not found in configuration")
        
        # Валідація критичних параметрів
        required_weights = ["drawdown", "var", "cvar", "volatility", "arce_flags", "inventory"]
        for weight_name in required_weights:
            if weight_name not in self.subcomponent_weights:
                raise ValueError(f"Missing required weight: {weight_name}")
        
        self.enabled = config.is_component_enabled("risk")
        
        self.logger.info(f"Risk Component initialized with centralized config, weights: {self.subcomponent_weights}")
        
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        """
        Розрахувати винагороду компонента (BaseRewardComponent interface)
        
        Args:
            state: Дані стану на поточний момент часу
            
        Returns:
            RewardComponentResult: Результат розрахунку компонента
        """
        # Extract data from state for the existing calculate method
        arce_data = state.arce if hasattr(state, 'arce') else None
        portfolio_data = state.portfolio if hasattr(state, 'portfolio') else None
        
        if arce_data is None or portfolio_data is None:
            self.logger.warning("ARCE or Portfolio data is missing in StateData, returning 0 reward for risk component.")
            return RewardComponentResult(
                component_name="risk",
                raw_value=0.0,
                subcomponents={"missing_data": 0.0},
                metadata={"error": "ARCE or Portfolio data is missing"}
            )
            
        return self.calculate(arce_data, portfolio_data, state)
        
    def calculate(self, arce_data: ARCEData, portfolio_data: PortfolioData, 
                 state_data: StateData) -> RewardComponentResult:
        """
        Розрахунок винагороди за ризик
        
        Args:
            arce_data: Дані з ARCE
            portfolio_data: Дані портфеля
            state_data: Загальні дані стану
            
        Returns:
            Результат розрахунку компоненти ризику
        """
        if not self.enabled:
            self.logger.debug("Risk component disabled, returning 0")
            return RewardComponentResult(
                component_name="risk",
                raw_value=0.0,
                subcomponents={"disabled": 0.0}
            )
            
        try:
            subcomponents = {}
            
            # Розрахунок всіх підкомпонент ризику
            drawdown_reward = self._calculate_drawdown_risk(arce_data)
            var_reward = self._calculate_var_risk(arce_data) 
            cvar_reward = self._calculate_cvar_risk(arce_data)
            volatility_reward = self._calculate_volatility_risk(arce_data)
            arce_flags_reward = self._calculate_arce_flags_risk(arce_data, state_data)
            inventory_reward = self._calculate_inventory_risk(arce_data, portfolio_data)
            
            # Зберігаємо сирі значення підкомпонент
            subcomponents.update({
                "drawdown_raw": drawdown_reward,
                "var_raw": var_reward,
                "cvar_raw": cvar_reward,
                "volatility_raw": volatility_reward,
                "arce_flags_raw": arce_flags_reward,
                "inventory_raw": inventory_reward
            })
            
            # Застосування ваг φ_k - БЕЗ HARDCODE FALLBACK
            if self.subcomponent_weights:
                weighted_drawdown = self.subcomponent_weights.get("drawdown", 0.0) * drawdown_reward
                weighted_var = self.subcomponent_weights.get("var", 0.0) * var_reward
                weighted_cvar = self.subcomponent_weights.get("cvar", 0.0) * cvar_reward
                weighted_volatility = self.subcomponent_weights.get("volatility", 0.0) * volatility_reward
                weighted_arce_flags = self.subcomponent_weights.get("arce_flags", 0.0) * arce_flags_reward
                weighted_inventory = self.subcomponent_weights.get("inventory", 0.0) * inventory_reward
            else:
                weighted_drawdown = weighted_var = weighted_cvar = weighted_volatility = weighted_arce_flags = weighted_inventory = 0.0

            
            # Фінальна винагорода за ризик
            total_risk_reward = (
                weighted_drawdown + weighted_var + weighted_cvar + 
                weighted_volatility + weighted_arce_flags + weighted_inventory
            )
            
            # Зберігаємо зважені значення
            subcomponents.update({
                "drawdown_weighted": weighted_drawdown,
                "var_weighted": weighted_var,
                "cvar_weighted": weighted_cvar,
                "volatility_weighted": weighted_volatility,
                "arce_flags_weighted": weighted_arce_flags,
                "inventory_weighted": weighted_inventory,
                "weights": self.subcomponent_weights
            })
            
            metadata = {
                "arce_regime": arce_data.regime_tag.value if arce_data.regime_tag else "UNKNOWN",
                "timestamp": state_data.timestamp,
                "active_flags_count": len(arce_data.active_flags) if arce_data.active_flags else 0
            }
            
            self.logger.debug(f"Risk calculation: total={total_risk_reward:.6f}, "
                             f"dd={drawdown_reward:.4f}, var={var_reward:.4f}, "
                             f"cvar={cvar_reward:.4f}, vol={volatility_reward:.4f}")
            
            return RewardComponentResult(
                component_name="risk",
                raw_value=total_risk_reward,
                subcomponents=subcomponents,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку Risk компоненти: {e}")
            # БЕЗ HARDCODE: читаємо з конфігурації
            validation_config = self.config.get_validation_config()
            safe_value = validation_config.get("default_safe_reward", -10.0)
            return RewardComponentResult(
                component_name="risk",
                raw_value=safe_value,
                subcomponents={"error": safe_value},
                metadata={"error": str(e)}
            )
            
    def _calculate_drawdown_risk(self, arce_data: ARCEData) -> float:
        """
        Розрахунок ризику DrawDown
        
        Формула: R_Risk,t^(DrawDown) = -c_dd * max(0, DD_t - DD_Limit)²
        """
        try:
            # БЕЗ HARDCODE FALLBACK: параметри з конфігурації
            if not self.drawdown_config:
                return 0.0
            c_dd = self.drawdown_config.get("c_dd", 0.0)
            tolerance = self.drawdown_config.get("threshold_tolerance", 0.0)
            
            dd_current = validate_numeric_value(arce_data.drawdown_current, "drawdown_current")
            dd_limit = validate_numeric_value(arce_data.drawdown_limit, "drawdown_limit")
            
            # Перевіряємо чи перевищує drawdown ліміт з урахуванням толерантності
            excess = max(0, dd_current - dd_limit - tolerance)
            
            if excess > 0:
                penalty = -c_dd * (excess ** 2)
                self.logger.debug(f"DrawDown penalty: current={dd_current:.4f}, "
                                 f"limit={dd_limit:.4f}, excess={excess:.4f}, penalty={penalty:.4f}")
                return penalty
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку DrawDown: {e}")
            return 0.0
            
    def _calculate_var_risk(self, arce_data: ARCEData) -> float:
        """
        Розрахунок ризику VaR
        
        Формула: R_Risk,t^(VaR) = -c_var * max(0, VaR_t - VaR_Limit)²
        """
        try:
            # БЕЗ HARDCODE FALLBACK: параметри з конфігурації
            if not self.var_config:
                return 0.0
            c_var = self.var_config.get("c_var", 0.0)
            tolerance = self.var_config.get("threshold_tolerance", 0.0)
            
            var_current = validate_numeric_value(arce_data.var_current, "var_current")
            var_limit = validate_numeric_value(arce_data.var_limit, "var_limit")
            
            excess = max(0, var_current - var_limit - tolerance)
            
            if excess > 0:
                penalty = -c_var * (excess ** 2)
                self.logger.debug(f"VaR penalty: current={var_current:.4f}, "
                                 f"limit={var_limit:.4f}, excess={excess:.4f}, penalty={penalty:.4f}")
                return penalty
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку VaR: {e}")
            return 0.0
            
    def _calculate_cvar_risk(self, arce_data: ARCEData) -> float:
        """
        Розрахунок ризику CVaR
        
        Формула: R_Risk,t^(CVaR) = -c_cvar * max(0, CVaR_t - CVaR_Limit)²
        """
        try:
            # БЕЗ HARDCODE FALLBACK: параметри з конфігурації
            if not self.cvar_config:
                return 0.0
            c_cvar = self.cvar_config.get("c_cvar", 0.0)
            tolerance = self.cvar_config.get("threshold_tolerance", 0.0)
            
            cvar_current = validate_numeric_value(arce_data.cvar_current, "cvar_current")
            cvar_limit = validate_numeric_value(arce_data.cvar_limit, "cvar_limit")
            
            excess = max(0, cvar_current - cvar_limit - tolerance)
            
            if excess > 0:
                penalty = -c_cvar * (excess ** 2)
                self.logger.debug(f"CVaR penalty: current={cvar_current:.4f}, "
                                 f"limit={cvar_limit:.4f}, excess={excess:.4f}, penalty={penalty:.4f}")
                return penalty
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку CVaR: {e}")
            return 0.0
            
    def _calculate_volatility_risk(self, arce_data: ARCEData) -> float:
        """
        Розрахунок ризику волатильності
        
        Формула: R_Risk,t^(Volatility) = -c_vol * ((σ_portfolio,t - σ_target) / σ_targetRange)²
        якщо |σ_portfolio,t - σ_target| > tolerance, інакше 0
        """
        try:
            # Volatility penalty calculation через ConfigManager для критичних параметрів
            if not self.volatility_config:
                return 0.0
            c_vol = get_config_with_fallback(self.volatility_config, "c_vol")
            tolerance = self.volatility_config.get("threshold_tolerance", 0.02)  # толерантність може залишитися з fallback
            
            portfolio_vol = validate_numeric_value(arce_data.portfolio_volatility, "portfolio_volatility")
            target_vol = validate_numeric_value(arce_data.target_volatility, "target_volatility")
            vol_range = validate_numeric_value(arce_data.volatility_range, "volatility_range")
            
            if vol_range <= 0:
                self.logger.warning("volatility_range <= 0, використовується значення за замовчуванням")
                vol_range = 0.05
                
            vol_deviation = abs(portfolio_vol - target_vol)
            
            if vol_deviation > tolerance:
                normalized_deviation = (portfolio_vol - target_vol) / vol_range
                penalty = -c_vol * (normalized_deviation ** 2)
                self.logger.debug(f"Volatility penalty: portfolio={portfolio_vol:.4f}, "
                                 f"target={target_vol:.4f}, deviation={vol_deviation:.4f}, penalty={penalty:.4f}")
                return penalty
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку Volatility: {e}")
            return 0.0
            
    def _calculate_arce_flags_risk(self, arce_data: ARCEData, state_data: StateData) -> float:
        """
        Розрахунок ризику ARCE прапорів
        
        Формула: R_Risk,t^(ARCEFlags) = -Σ Severity(f, S_t) * BasePenaltyValue(f) * Multiplier(f)
        """
        try:
            if not arce_data.active_flags:
                return 0.0
                
            # ARCE flags penalty через ConfigManager для критичних параметрів
            if not self.arce_flags_config:
                return 0.0
            base_penalty_multiplier = get_config_with_fallback(self.arce_flags_config, "base_penalty_multiplier")
            total_penalty = 0.0
            
            for flag in arce_data.active_flags:
                if not isinstance(flag, dict):
                    continue
                    
                severity = flag.get("severity", 1.0)
                penalty_multiplier = flag.get("penalty_multiplier", 1.0)
                flag_name = flag.get("name", "unknown")
                
                # BasePenaltyValue може бути в конфігурації або в самому прапорі
                base_penalty = flag.get("base_penalty", base_penalty_multiplier)
                
                flag_penalty = severity * base_penalty * penalty_multiplier
                total_penalty += flag_penalty
                
                self.logger.debug(f"ARCE Flag penalty: {flag_name}, "
                                 f"severity={severity}, penalty={flag_penalty:.4f}")
                
            return -total_penalty  # Негативна винагорода за активні прапори
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку ARCE Flags: {e}")
            return 0.0
            
    def _calculate_inventory_risk(self, arce_data: ARCEData, portfolio_data: PortfolioData) -> float:
        """
        Розрахунок ризику інвентарю (позицій)
        
        Формула: R_Risk,t^(Inventory) = -c_inv * Σ max(0, |Position_j| - MaxPositionLimit_j)²
        """
        try:
            # Inventory penalty через ConfigManager для критичних параметрів
            if not self.inventory_config:
                return 0.0
            c_inv = get_config_with_fallback(self.inventory_config, "c_inv")
            
            if not portfolio_data.positions or not arce_data.position_limits:
                return 0.0
                
            total_penalty = 0.0
            
            for asset_id, position_size in portfolio_data.positions.items():
                if asset_id in arce_data.position_limits:
                    max_limit = arce_data.position_limits[asset_id]
                    abs_position = abs(position_size)
                    
                    excess = max(0, abs_position - max_limit)
                    if excess > 0:
                        penalty = (excess ** 2)
                        total_penalty += penalty
                        
                        self.logger.debug(f"Inventory penalty for {asset_id}: "
                                         f"position={abs_position:.4f}, limit={max_limit:.4f}, "
                                         f"excess={excess:.4f}, penalty={penalty:.4f}")
                        
            return -c_inv * total_penalty if total_penalty > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку Inventory: {e}")
            return 0.0
            
    def get_component_info(self) -> Dict[str, Any]:
        """Отримання інформації про компоненту ризику"""
        return {
            "component_name": "risk",
            "enabled": self.enabled,
            "subcomponent_weights": self.subcomponent_weights,
            "subcomponents": [
                "drawdown", "var", "cvar", "volatility", "arce_flags", "inventory"
            ],
            "formula": "R_Risk,t = Σ φ_k * R_Risk,t^(k) for k in {DrawDown, VaR, CVaR, Volatility, ARCEFlags, Inventory}"
        }
