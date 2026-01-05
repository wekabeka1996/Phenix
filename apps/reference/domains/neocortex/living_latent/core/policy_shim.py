#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
POLICY SHIM: Інтелектуальний перехоплювач дій перед no_op
Компонент для усунення консервативного lock та no_op стріків

Мета: коли R0 Rule-Based Policy обирає no_op, замінити на cooloff_sleep
в ситуаціях консервативного блокування або no_op стріків.

V2: State-based approach без глобальних змінних
"""

import logging
from typing import List, Protocol, Optional

logger = logging.getLogger(__name__)

# Константи для налаштування поведінки
NOOP_STREAK_LIMIT = 2  # Агресивніша заміна для канарки
CONSERVATIVE_TICKS_FOR_HINT = 8  # Швидша детекція консервативного lock

class Safety(Protocol):
    """Протокол для об'єкта контролю безпеки"""
    def is_allowed(self, name: str) -> bool: ...
    def is_rate_limited(self, name: str) -> bool: ...

def _inc(state, key: str, by: int = 1, reset_if_lt=None) -> int:
    """Інкрементувати лічильник у state.flags"""
    flags = getattr(state, "flags", None)
    if flags is None:
        state.flags = {}
        flags = state.flags
    if reset_if_lt is not None and flags.get(reset_if_lt, 0) < reset_if_lt:
        flags[key] = 0
    flags[key] = flags.get(key, 0) + by
    return flags[key]

def _get(state, key: str, default: int = 0) -> int:
    """Отримати значення з state.flags"""
    flags = getattr(state, "flags", None)
    return (flags or {}).get(key, default)

def _set(state, key: str, val: int) -> None:
    """Встановити значення в state.flags"""
    if getattr(state, "flags", None) is None:
        state.flags = {}
    state.flags[key] = val

def conservative_lock_hint(state, bridge_count: int) -> bool:
    """
    Детектор консервативного блокування на основі кількості мостів
    
    Args:
        state: Об'єкт стану з flags
        bridge_count: Поточна кількість валідних мостів
        
    Returns:
        True якщо система ймовірно у консервативному режимі
    """
    if bridge_count >= 5:
        ticks = _inc(state, "conservative_ticks", by=1)
    else:
        _set(state, "conservative_ticks", 0)
        ticks = 0
    
    is_conservative = ticks >= CONSERVATIVE_TICKS_FOR_HINT
    
    if is_conservative:
        logger.info(f"🔒 CONSERVATIVE LOCK DETECTED: bridges={bridge_count}, ticks={ticks}")
    
    return is_conservative

def choose_safe_action(
    state,
    primary: str,
    ranked: List[str],
    safety: Safety,
    bridge_count: int,
    prefer_actions_for_next_ticks: int = 0,
) -> str:
    """
    Інтелектуальний вибір безпечної дії з урахуванням:
    - заблокованих/лімітованих (fallback на наступну дозволену)
    - no_op-стріку/консервативного патерну (м'яка заміна на cooloff_sleep)
    - м'якого форсингу (тимчасовий прапор на кілька тиків)
    
    Args:
        state: Об'єкт стану для збереження лічільників
        primary: Дія обрана R0 rule-based політикою
        ranked: Список кандидатів за скором
        safety: Об'єкт з перевірками безпеки
        bridge_count: Поточна кількість мостів
        prefer_actions_for_next_ticks: Примусово віддавати перевагу діям
        
    Returns:
        Фінальна дія для виконання
    """
    import os
    from living_latent.common.signal_bus import BUS
    
    # 🔒 Kill-switch для Policy Shim
    if os.getenv("LLA_POLICY_SHIM_MODE", "").lower() in ("off", "disabled", "0"):
        logger.info(f"🚫 Policy Shim DISABLED by env var - returning primary action: {primary}")
        return primary
    
    # 🔒 Повага до Governor (навіть якщо shim увімкнено)
    gov = BUS.get_governor()
    if gov:
        # Якщо bandcap/мін-noops активні або ін'єкції заборонені - не переписуємо no_op
        can_inject = hasattr(gov, "can_inject") and gov.can_inject()
        noops_left = getattr(gov, "_noops_left", 0)
        
        if not can_inject or noops_left > 0:
            logger.info(f"🔒 Governor ENFORCEMENT: can_inject={can_inject}, noops_left={noops_left} - keeping {primary}")
            return primary
    
    logger.debug(f"Policy shim: primary={primary}, ranked={ranked}, bridges={bridge_count}")
    
    # 1) Якщо первинна дія заблокована - використовуємо fallback
    if not safety.is_allowed(primary) or safety.is_rate_limited(primary):
        logger.info(f"🚫 PRIMARY ACTION BLOCKED: {primary}")
        
        # Пробуємо ranked кандидатів
        for candidate in ranked:
            if safety.is_allowed(candidate) and not safety.is_rate_limited(candidate):
                logger.info(f"✅ FALLBACK TO RANKED: {candidate}")
                _set(state, "noop_streak", 0)  # Скидаємо стрік
                return candidate
        
        # М'який fallback на безпечні мікро-дії
        safe_alternatives = ["micro_probe", "log_marker", "cooloff_sleep"]
        for alt in safe_alternatives:
            if safety.is_allowed(alt) and not safety.is_rate_limited(alt):
                logger.info(f"🔧 FALLBACK TO {alt.upper()}")
                _set(state, "noop_streak", 0)
                return alt
        
        logger.warning(f"⚪ FALLBACK TO NO_OP (no alternatives)")
        return "no_op"
    
    # 2) Ключова логіка: якщо вибраний no_op - спробувати м'яку заміну
    if primary == "no_op":
        streak = _inc(state, "noop_streak", by=1)
        hint = conservative_lock_hint(state, bridge_count)
        prefer = (streak >= NOOP_STREAK_LIMIT) or hint or (prefer_actions_for_next_ticks > 0)
        
        # Оновлюємо таймер з останнього не-no_op
        _inc(state, "since_last_non_noop_s", by=5)  # Приблизно 5с між циклами
        
        logger.info(f"⚪ NO_OP SELECTED: streak={streak}, conservative={hint}, prefer={prefer_actions_for_next_ticks}")
        
        if prefer and safety.is_allowed("micro_probe") and not safety.is_rate_limited("micro_probe"):
            logger.info(f"🎯 POLICY_SHIM: replacing no_op→micro_probe "
                       f"(streak={streak}, bridge_count={bridge_count}, prefer_ticks={prefer_actions_for_next_ticks})")
            _set(state, "noop_streak", 0)  # Скидаємо стрік після заміни
            _set(state, "since_last_non_noop_s", 0)  # Скидаємо таймер
            return "micro_probe"
        elif prefer and safety.is_allowed("cooloff_sleep") and not safety.is_rate_limited("cooloff_sleep"):
            logger.info(f"🎯 POLICY_SHIM: replacing no_op→cooloff_sleep "
                       f"(streak={streak}, bridge_count={bridge_count}, prefer_ticks={prefer_actions_for_next_ticks})")
            _set(state, "noop_streak", 0)  # Скидаємо стрік після заміни
            _set(state, "since_last_non_noop_s", 0)  # Скидаємо таймер
            return "cooloff_sleep"
        
        # М'який страхувальний тригер для гарантованої заміни
        since_last_non_noop = _get(state, "since_last_non_noop_s", 0)
        if since_last_non_noop >= 90:
            # Пріоритет: micro_probe → cooloff_sleep  
            for emergency_action in ["micro_probe", "cooloff_sleep"]:
                if (safety.is_allowed(emergency_action) and 
                    not safety.is_rate_limited(emergency_action)):
                    logger.info(f"🔧 POLICY_SHIM: emergency replacement after {since_last_non_noop}s without action → {emergency_action}")
                    _set(state, "noop_streak", 0)
                    _set(state, "since_last_non_noop_s", 0)
                    return emergency_action
        
        logger.info(f"⚪ KEEPING NO_OP: streak={streak}, since_non_noop={since_last_non_noop}s")
        return "no_op"
    
    # 3) Звичайна дозволена дія - скидаємо лічільники
    _set(state, "noop_streak", 0)
    _set(state, "since_last_non_noop_s", 0)  # Скидаємо таймер при реальній дії
    logger.debug(f"✅ KEEPING PRIMARY ACTION: {primary}")
    return primary

def get_shim_stats(state) -> dict:
    """Отримати статистику shim'а для моніторингу"""
    flags = getattr(state, "flags", {})
    return {
        "conservative_ticks": flags.get("conservative_ticks", 0),
        "noop_streak": flags.get("noop_streak", 0),
        "conservative_active": flags.get("conservative_ticks", 0) >= CONSERVATIVE_TICKS_FOR_HINT,
        "prefer_actions_for_next_ticks": flags.get("prefer_actions_for_next_ticks", 0)
    }

def reset_shim_state(state):
    """Скинути стан shim'а (для тестування)"""
    state.flags = {
        "conservative_ticks": 0,
        "noop_streak": 0,
        "prefer_actions_for_next_ticks": 0
    }
    logger.info("🔄 POLICY SHIM STATE RESET")

def activate_prefer_actions(state, ticks: int = 5):
    """Активувати м'який пріоритет дій на кілька тіків"""
    if getattr(state, "flags", None) is None:
        state.flags = {}
    current = state.flags.get("prefer_actions_for_next_ticks", 0)
    state.flags["prefer_actions_for_next_ticks"] = max(current, ticks)
    logger.info(f"🎯 ACTIVATED PREFER ACTIONS for {ticks} ticks")