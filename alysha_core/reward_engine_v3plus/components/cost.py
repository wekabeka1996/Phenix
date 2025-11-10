"""
Cost Reward Component для ALYSHA-RE-V3+ 

Компонент розрахунку винагороди за витрати транзакцій та операцій.

Основна формула:
R_Cost,t = -α_bid_ask * BidAskCost_t - α_transaction * TransactionCost_t - α_slippage * SlippageCost_t

Автор: ALYSHA система
Версія: V3+
"""

import logging
from typing import Dict, Any, Optional, cast
from ..data_types import ARCEData, PortfolioData, StateData, RewardComponentResult, ExecutionData
from ..utils import RewardEngineConfig, validate_numeric_value, safe_divide
from .base import BaseRewardComponent


class CostRewardComponent(BaseRewardComponent):
    """
    Компонент винагороди за витрати
    
    Розраховує негативну винагороду за різні типи витрат:
    - Bid-Ask спреди
    - Транзакційні витрати
    - Проковзування (slippage)
    """
    
    def __init__(self, config: RewardEngineConfig):
        # BaseRewardComponent очікує Dict[str, Any]; передаємо через cast
        super().__init__(cast(Any, config))  # type: ignore[arg-type]
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Отримуємо конфігурацію для компоненти витрат
        cost_config = config.get_component_config("cost")
        
        # Коефіцієнти для різних типів витрат
        self.alpha_bid_ask = cost_config.get("alpha_bid_ask", 1.0)
        self.alpha_transaction = cost_config.get("alpha_transaction", 1.0) 
        self.alpha_slippage = cost_config.get("alpha_slippage", 2.0)
        
        # Конфігурація підкомпонент
        self.bid_ask_config = cost_config.get("bid_ask", {})
        self.transaction_config = cost_config.get("transaction", {})
        self.slippage_config = cost_config.get("slippage", {})
        
        self.enabled = config.is_component_enabled("cost")
        
        self.logger.info(f"Cost Component initialized with alphas: "
                        f"bid_ask={self.alpha_bid_ask}, transaction={self.alpha_transaction}, "
                        f"slippage={self.alpha_slippage}")
        
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
        return self.calculate(arce_data, portfolio_data, state)
        
    def calculate(self,
                 arce_data: Optional[ARCEData],          # ← allow None
                 portfolio_data: Optional[PortfolioData],  # ← allow None
                 state_data: StateData) -> RewardComponentResult:
        """
        Розрахунок винагороди за витрати
        
        Args:
            arce_data: Дані з ARCE системи
            portfolio_data: Дані портфеля
            state_data: Загальні дані стану
            
        Returns:
            Результат розрахунку компоненти витрат
        """
        if not self.enabled:
            self.logger.debug("Cost component disabled, returning 0")
            return RewardComponentResult(
                component_name="cost",
                raw_value=0.0,
                subcomponents={"disabled": 0.0}
            )
            
        try:
            # Розрахунок всіх підкомпонент витрат
            bid_ask_cost = self._calculate_bid_ask_cost(state_data)
            transaction_cost = self._calculate_transaction_cost(state_data)
            slippage_cost = self._calculate_slippage_cost(state_data)
            
            # Загальна винагорода за витрати (негативна)
            total_cost_reward = (
                -self.alpha_bid_ask * bid_ask_cost - 
                self.alpha_transaction * transaction_cost -
                self.alpha_slippage * slippage_cost
            )
            
            # Підкомпоненти для детального аналізу
            subcomponents = {
                "bid_ask_cost": bid_ask_cost,
                "transaction_cost": transaction_cost,
                "slippage_cost": slippage_cost,
                "bid_ask_weighted": -self.alpha_bid_ask * bid_ask_cost,
                "transaction_weighted": -self.alpha_transaction * transaction_cost,
                "slippage_weighted": -self.alpha_slippage * slippage_cost
            }
            
            self.logger.debug(f"Cost calculation: total={total_cost_reward:.6f}, "
                             f"bid_ask={bid_ask_cost:.6f}, transaction={transaction_cost:.6f}, "
                             f"slippage={slippage_cost:.6f}")
            
            return RewardComponentResult(
                component_name="cost",
                raw_value=total_cost_reward,
                subcomponents=subcomponents
            )
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку Cost component: {e}")
            safe_reward = self.config.get_validation_config().get("default_safe_reward", -10.0)
            return RewardComponentResult(
                component_name="cost",
                raw_value=safe_reward,
                subcomponents={"error": safe_reward}      # float for Dict[str, float]
             )
            
    def _calculate_bid_ask_cost(self, state_data: StateData) -> float:
        """
        Розрахунок витрат на bid-ask спреди
        
        Args:
            state_data: Дані стану з інформацією про виконання торгів
            
        Returns:
            Нормалізовані витрати на спреди
        """
        try:
            if not hasattr(state_data, 'execution') or state_data.execution is None:
                return 0.0
                
            execution_data = state_data.execution
            if not hasattr(execution_data, 'bid_ask_spreads') or not execution_data.bid_ask_spreads:
                return 0.0
                
            total_spread_cost = 0.0
            total_volume = 0.0
            
            # Розрахунок середньозваженої вартості спредів
            for asset_id, spread_data in execution_data.bid_ask_spreads.items():
                if isinstance(spread_data, dict):
                    spread = spread_data.get('spread', 0.0)
                    volume = spread_data.get('volume', 0.0)
                else:
                    spread = spread_data
                    volume = 1.0  # За замовчуванням
                    
                if volume > 0:
                    total_spread_cost += spread * volume
                    total_volume += volume
                    
            if total_volume > 0:
                average_spread_cost = safe_divide(total_spread_cost, total_volume)
                
                # Нормалізація відносно порогу
                threshold = self.bid_ask_config.get("cost_threshold", 0.001)
                normalized_cost = safe_divide(average_spread_cost, threshold)
                
                self.logger.debug(f"Bid-ask cost: avg_spread={average_spread_cost:.6f}, "
                                 f"normalized={normalized_cost:.6f}")
                
                return normalized_cost
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку bid-ask витрат: {e}")
            return 0.0
            
    def _calculate_transaction_cost(self, state_data: StateData) -> float:
        """
        Розрахунок транзакційних витрат (комісії, fees)
        
        Args:
            state_data: Дані стану з інформацією про виконання торгів
            
        Returns:
            Нормалізовані транзакційні витрати
        """
        try:
            if not hasattr(state_data, 'execution') or state_data.execution is None:
                return 0.0
                
            execution_data = state_data.execution
            if not hasattr(execution_data, 'transaction_fees') or not execution_data.transaction_fees:
                return 0.0
                
            total_fees = 0.0
            total_volume = 0.0
            
            # Агрегація комісій по всіх активах
            for asset_id, fee_data in execution_data.transaction_fees.items():
                if isinstance(fee_data, dict):
                    fee = fee_data.get('fee', 0.0)
                    volume = fee_data.get('volume', 0.0)
                else:
                    fee = fee_data
                    volume = 1.0  # За замовчуванням
                    
                if volume > 0:
                    total_fees += fee
                    total_volume += volume
                    
            if total_volume > 0:
                # Нормалізація відносно базового об'єму портфеля
                base_volume = self.transaction_config.get("base_volume", 1000.0)
                fee_rate = safe_divide(total_fees, total_volume)
                normalized_cost = safe_divide(fee_rate * total_volume, base_volume)
                
                self.logger.debug(f"Transaction cost: total_fees={total_fees:.6f}, "
                                 f"fee_rate={fee_rate:.6f}, normalized={normalized_cost:.6f}")
                
                return normalized_cost
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку транзакційних витрат: {e}")
            return 0.0
            
    def _calculate_slippage_cost(self, state_data: StateData) -> float:
        """
        Розрахунок витрат на проковзування (slippage)
        
        Args:
            state_data: Дані стану з інформацією про виконання торгів
            
        Returns:
            Нормалізовані витрати на проковзування
        """
        try:
            if not hasattr(state_data, 'execution') or state_data.execution is None:
                return 0.0
                
            execution_data = state_data.execution
            if not hasattr(execution_data, 'slippage_costs') or not execution_data.slippage_costs:
                return 0.0
                
            total_slippage = 0.0
            total_volume = 0.0
            
            # Агрегація проковзування по всіх активах
            for asset_id, slippage_data in execution_data.slippage_costs.items():
                if isinstance(slippage_data, dict):
                    slippage = slippage_data.get('slippage', 0.0)
                    volume = slippage_data.get('volume', 0.0)
                    expected_price = slippage_data.get('expected_price', 1.0)
                    actual_price = slippage_data.get('actual_price', 1.0)
                    
                    # Розрахунок проковзування як відсоток відхилення
                    if expected_price > 0:
                        calculated_slippage = abs(actual_price - expected_price) / expected_price
                        slippage = max(slippage, calculated_slippage)
                else:
                    slippage = slippage_data
                    volume = 1.0  # За замовчуванням
                    
                if volume > 0:
                    total_slippage += slippage * volume
                    total_volume += volume
                    
            if total_volume > 0:
                average_slippage = safe_divide(total_slippage, total_volume)
                
                # Нормалізація відносно порогу проковзування
                threshold = self.slippage_config.get("slippage_threshold", 0.005)
                normalized_cost = safe_divide(average_slippage, threshold)
                
                self.logger.debug(f"Slippage cost: avg_slippage={average_slippage:.6f}, "
                                 f"normalized={normalized_cost:.6f}")
                
                return normalized_cost
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку slippage витрат: {e}")
            return 0.0
            
    def get_component_info(self) -> Dict[str, Any]:
        """Отримання інформації про компоненту витрат"""
        return {
            "component_name": "cost",
            "enabled": self.enabled,
            "alpha_coefficients": {
                "bid_ask": self.alpha_bid_ask,
                "transaction": self.alpha_transaction,
                "slippage": self.alpha_slippage
            },
            "subcomponents": [
                "bid_ask_cost",
                "transaction_cost", 
                "slippage_cost"
            ],
            "description": "Розрахунок негативної винагороди за витрати на торгівлю"
        }
