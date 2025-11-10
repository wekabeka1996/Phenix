"""
Компоненти винагородної системи ALYSHA-RE-V3+

Цей пакет містить усі компоненти винагороди згідно з математичними формулами:
- PnL: $R_{PnL,t}$ - прибутки та збитки  
- Risk: $R_{Risk,t}$ - ризикові компоненти (DrawDown, VaR, CVaR, Volatility, ARCE Flags, Inventory)
- RiskReward: $R_{RiskReward,t}$ - інтеграція з RiskManager (TASK 5)
- Cost: $R_{Cost,t}$ - витрати (комісії, slippage, market impact)
- Behavior: $R_{Behavior,t}$ - формування поведінки (overtrading, flickering) 
- Information: $R_{Information,t}$ - використання інформації (signal alignment, exploration)
- Event: $R_{Event,t}$ - дискретні події
- Shaping: $R_{Shaping,t}$ - формування винагороди через потенціали

PRODUCTION COMPONENTS: Складна, потужна система компонентів
"""

__all__ = [
    # Production components - COMPLEX BY DESIGN
    'RiskRewardComponent'  # Main production risk reward component
]

# Import production components
try:
    from .risk_reward import RiskRewardComponent
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Risk reward component not available: {e}")
    RiskRewardComponent = None
