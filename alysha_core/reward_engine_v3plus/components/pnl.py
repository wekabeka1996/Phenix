"""
PnL Reward Component для ALYSHA-RE-V3+

Реалізація компоненти винагороди за прибутки та збитки згідно з формулою:
R_PnL,t = c_real * RealizedPnL_t + c_unreal * UnrealizedPnL_t

Компонента враховує:
- Реалізований PnL від виконаних угод
- Нереалізований PnL від відкритих позицій  
- Масштабування коефіцієнтами з конфігурації
"""

import logging
from typing import Dict, Any
import numpy as np

from ..data_types import (
    PnLData, StateData, RewardComponentResult, ConfigDict
)
from ..utils import validate_numeric_value, RewardEngineConfig
from .base import BaseRewardComponent


class PnLRewardComponent(BaseRewardComponent):
    """
    Компонента винагороди за PnL
    
    Математична формула:
    R_PnL,t = c_real * RealizedPnL_t + c_unreal * UnrealizedPnL_t
    
    де:
    - c_real, c_unreal - коефіцієнти масштабування з конфігурації  
    - RealizedPnL_t - реалізований прибуток/збиток на кроці t
    - UnrealizedPnL_t - нереалізований прибуток/збиток на кроці t
    """
    
    def __init__(self, config: RewardEngineConfig):
        """
        Ініціалізація компоненти PnL
        
        Args:
            config: Конфігурація reward engine
        """
        # ⬇️ 1) Спочатку отримуємо словник конфігурації підкомпонента
        pnl_config = config.get_component_config("pnl")
        
        # ⬇️ 2) Передаємо саме словник у базовий клас
        super().__init__(pnl_config)
        
        # ⬇️ 3) Зберігаємо повну конфігурацію для подальшого доступу
        self.config = config
        self.logger = logging.getLogger("alysha_reward_engine.pnl")
        
        # Завантаження параметрів з конфігурації
        pnl_config = config.get_component_config("pnl")
        
        self.c_real = pnl_config.get("realized_pnl", {}).get("scaling_factor", 1.0)
        self.c_unreal = pnl_config.get("unrealized_pnl", {}).get("scaling_factor", 0.8)
        
        self.realized_weight = pnl_config.get("realized_pnl", {}).get("weight", 1.0)
        self.unrealized_weight = pnl_config.get("unrealized_pnl", {}).get("weight", 0.8)
        
        self.enabled = config.is_component_enabled("pnl")
        
        self.logger.info(f"PnL Component initialized: c_real={self.c_real}, c_unreal={self.c_unreal}")
        
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        """
        Розрахувати винагороду компонента (BaseRewardComponent interface)
        
        Args:
            state: Дані стану на поточний момент часу
            
        Returns:
            RewardComponentResult: Результат розрахунку компонента
        """
        return self.calculate(state)
        
    def calculate(self, state_data: StateData) -> RewardComponentResult:
        """
        Розрахунок винагороди за PnL
        
        Args:
            state_data: Дані стану з PnL інформацією
            
        Returns:
            Результат розрахунку компоненти PnL
            
        Raises:
            ValueError: Якщо дані некоректні
        """
        if not self.enabled:
            self.logger.debug("PnL component disabled, returning 0")
            return RewardComponentResult(
                component_name="pnl",
                raw_value=0.0,
                subcomponents={"disabled": 0.0}
            )
            
        try:
            # Валідація вхідних даних
            if not state_data.pnl:
                raise ValueError("PnL дані відсутні в state_data")
                
            pnl_data = state_data.pnl
            
            # Валідація числових значень
            realized_pnl = validate_numeric_value(
                pnl_data.realized_pnl, 
                "realized_pnl",
                allow_nan=False,
                allow_inf=False
            )
            
            unrealized_pnl = validate_numeric_value(
                pnl_data.unrealized_pnl,
                "unrealized_pnl", 
                allow_nan=False,
                allow_inf=False
            )
            
            # Розрахунок компонент PnL згідно з формулою
            realized_component = self.c_real * realized_pnl
            unrealized_component = self.c_unreal * unrealized_pnl
            
            # Загальна винагорода PnL
            total_pnl_reward = (
                self.realized_weight * realized_component + 
                self.unrealized_weight * unrealized_component
            )
            
            # Детальна інформація для логування
            subcomponents = {
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl, 
                "realized_component": realized_component,
                "unrealized_component": unrealized_component,
                "c_real": self.c_real,
                "c_unreal": self.c_unreal,
                "realized_weight": self.realized_weight,
                "unrealized_weight": self.unrealized_weight
            }
            
            metadata = {
                "asset_pnl": pnl_data.asset_pnl if hasattr(pnl_data, 'asset_pnl') else {},
                "timestamp": state_data.timestamp
            }
            
            self.logger.debug(f"PnL calculation: realized={realized_pnl:.6f}, "
                             f"unrealized={unrealized_pnl:.6f}, total_reward={total_pnl_reward:.6f}")
            
            return RewardComponentResult(
                component_name="pnl",
                raw_value=total_pnl_reward,
                subcomponents=subcomponents,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку PnL компоненти: {e}")
            # Повертаємо безпечне значення при помилці
            safe_value = self.config.get("validation.default_safe_reward", -10.0)
            return RewardComponentResult(
                component_name="pnl",
                raw_value=safe_value,
                subcomponents={"error": safe_value},
                metadata={"error": str(e)}
            )
    
    def validate_pnl_data(self, pnl_data: PnLData) -> bool:
        """
        Валідація PnL даних
        
        Args:
            pnl_data: Дані PnL для валідації
            
        Returns:
            True якщо дані валідні, False інакше
        """
        try:
            validate_numeric_value(pnl_data.realized_pnl, "realized_pnl")
            validate_numeric_value(pnl_data.unrealized_pnl, "unrealized_pnl")
            return True
        except ValueError as e:
            self.logger.warning(f"PnL дані не пройшли валідацію: {e}")
            return False
            
    def get_component_info(self) -> Dict[str, Any]:
        """
        Отримання інформації про компоненту
        
        Returns:
            Словник з інформацією про налаштування компоненти
        """
        return {
            "component_name": "pnl",
            "enabled": self.enabled,
            "c_real": self.c_real,
            "c_unreal": self.c_unreal,
            "realized_weight": self.realized_weight,
            "unrealized_weight": self.unrealized_weight,
            "formula": "R_PnL,t = realized_weight * (c_real * RealizedPnL_t) + unrealized_weight * (c_unreal * UnrealizedPnL_t)"
        }
