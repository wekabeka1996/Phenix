#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
ACTION GOVERNOR: PI-контролер для утримання action_ratio в цільовому коридорі
SPEC: AR-010-GOVERNOR - Governor для продакшн-готового action ratio targeting

Функції:
- EWMA фільтрація action_ratio_60s для згладжування
- PI-контролер з антивіндап для стабільного управління
- Динамічне управління prefer_actions duty cycle
- Адаптивна noop_penalty для м'якого штрафу
- Жорсткі квоти безпеки проти оверактивності

Цілі:
- Утримання action_ratio в межах target ±4% (18-26% для target=22%)
- Запобігання залипанню на одній мікродії
- Стабільність під час флуктуацій системного навантаження
"""

import logging
import os
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

@dataclass
class GovernorConfig:
    """Конфігурація Action Governor"""
    target_pct: float = 22.0        # Цільовий action ratio (%)
    tolerance_pct: float = 4.0      # Допуск ±4% (18-26%)
    
    # PI-контролер параметри
    kp: float = 0.5                 # Пропорційний коефіцієнт
    ki: float = 0.1                 # Інтегральний коефіцієнт
    
    # EWMA згладжування
    alpha: float = 0.2              # EWMA коефіцієнт (вищий = швидше реагування)
    
    # Управління prefer_actions
    prefer_ticks_max: int = 12      # Максимальна довжина prefer window
    duty_cycle_max: float = 0.35    # Максимальна частка часу в prefer ON
    
    # noop_penalty адаптація
    noop_penalty_base: float = 0.08 # Базовий штраф за no_op
    noop_penalty_min: float = 0.02  # Мінімальний штраф
    noop_penalty_max: float = 0.15  # Максимальний штраф
    noop_penalty_gain: float = 0.5  # Коефіцієнт адаптації штрафу
    
    # Антивіндап
    integral_max: float = 50.0      # Максимальна інтегральна складова
    
    # Квоти безпеки
    max_injections_per_min: int = 10     # Максимум форсованих дій за хвилину
    action_cooldown_s: float = 5.0       # Мінімальна затримка між однаковими діями
    
    # BandCap: жорстка пауза коли вище смуги
    bandcap_s: float = 20.0             # Секунди блокування при виході за верхню межу
    min_noops_after_action: int = 4     # Мінімальні no-op слоти після ефективної дії (K=4 → ~20%)
    
    # Environment overrides
    @classmethod
    def from_env(cls) -> 'GovernorConfig':
        """Створити конфігурацію з environment змінних"""
        return cls(
            target_pct=float(os.environ.get('LLA_ACTION_TARGET_PCT', 22.0)),
            tolerance_pct=float(os.environ.get('LLA_GOVERNOR_TOLERANCE_PCT', 4.0)),
            kp=float(os.environ.get('LLA_GOVERNOR_KP', 0.2)),
            ki=float(os.environ.get('LLA_GOVERNOR_KI', 0.05)),
            alpha=float(os.environ.get('LLA_GOVERNOR_EWMA_ALPHA', 0.4)),
            duty_cycle_max=float(os.environ.get('LLA_ACTION_MAX_DUTY', 0.35)),
            max_injections_per_min=int(os.environ.get('LLA_ACTION_MAX_INJECTIONS_PER_MIN', 3)),
            action_cooldown_s=float(os.environ.get('LLA_ACTION_COOLDOWN_SECONDS', 10.0)),
            prefer_ticks_max=int(os.environ.get('LLA_GOVERNOR_PREFER_TICKS_MAX', 1)),
            bandcap_s=float(os.environ.get('LLA_GOVERNOR_BANDCAP_S', 20.0)),
            min_noops_after_action=int(os.environ.get('LLA_GOVERNOR_MIN_NOOPS_AFTER_ACTION', 4)),
        )

class ActionGovernor:
    """
    PI-контролер для утримання action_ratio в цільовому коридорі
    
    Архітектура:
    1. EWMA фільтрація вхідного action_ratio для згладжування
    2. PI-контролер з антивіндап для обчислення керуючого сигналу
    3. Динамічне управління prefer_actions window і noop_penalty
    4. Квоти безпеки і антиспам для запобігання оверактивності
    """
    
    def __init__(self, config: Optional[GovernorConfig] = None):
        self.config = config or GovernorConfig.from_env()
        
        # Стан PI-контролера
        self.ratio_ewma: float = self.config.target_pct
        self.integral: float = 0.0
        self.last_update_time: Optional[float] = None
        
        # Статистика та квоти
        self.injection_timestamps: deque = deque(maxlen=100)  # Для квот
        self.action_last_used: Dict[str, float] = defaultdict(float)  # Для cooldown
        self.usage_counts_60s: Dict[str, deque] = defaultdict(lambda: deque(maxlen=120))  # 60s at 0.5Hz
        
        # BandCap стан
        self._bandcap_until: float = 0.0    # Час до якого блокуємо ін'єкції
        self.band_violations: int = 0       # Лічильник порушень діапазону
        
        # Мінімальні no-op після дії
        self._noops_left: int = 0           # Скільки no-op слотів залишилось
        
        # Метрики для логування
        self.metrics_history: deque = deque(maxlen=100)
        
        logger.info(f"ActionGovernor initialized: target={self.config.target_pct}%, "
                   f"tolerance=±{self.config.tolerance_pct}%, duty_max={self.config.duty_cycle_max}")
        
    def notify_effective_action(self) -> None:
        """Викликати коли ефективна дія застосована - запускає мінімальну паузу"""
        self._noops_left = max(self._noops_left, self.config.min_noops_after_action)
        logger.info(f"🔄 EFFECTIVE ACTION: forcing next {self._noops_left} decisions to be no-ops (K={self.config.min_noops_after_action})")
        
        
    def can_inject(self) -> bool:
        """Перевіряє чи можна робити ін'єкцію зараз"""
        current_time = time.time()
        
        # BandCap check
        band_locked = current_time < self._bandcap_until
        if band_locked:
            logger.debug(f"🚫 BandCap blocking injection (locked until {self._bandcap_until})")
            return False
            
        # Min noops check (K parameter математичний контроль)
        if self._noops_left > 0:
            logger.info(f"� K={self.config.min_noops_after_action} ENFORCEMENT: {self._noops_left} mandatory no-ops remaining")
            return False
            
        return True
    
    def notify_noop_executed(self):
        """Викликається після виконання no-op дії"""
        if self._noops_left > 0:
            self._noops_left -= 1
            logger.info(f"🔄 K-enforcement: no-op executed, {self._noops_left} mandatory slots remaining")
        else:
            logger.debug(f"🔄 No-op executed (not part of K-enforcement)")
    
    def update(self, action_ratio_pct: float, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Оновити стан контролера та отримати керуючі сигнали
        
        Args:
            action_ratio_pct: Поточний action ratio (%)
            timestamp: Час оновлення (якщо None - використовується time.time())
            
        Returns:
            Dict з керуючими сигналами:
            - prefer_ticks: Рекомендована довжина prefer_actions window
            - noop_penalty: Рекомендований штраф за no_op
            - duty_cycle: Поточний duty cycle
            - in_tolerance: True якщо в межах допуску
            - error: Поточна помилка (target - actual)
        """
        current_time = timestamp or time.time()
        
        # BandCap: якщо вийшли вище верхньої межі — блокуємо ін'єкції на короткий час
        upper_limit = self.config.target_pct + self.config.tolerance_pct
        if action_ratio_pct > upper_limit:
            self._bandcap_until = current_time + self.config.bandcap_s
            self.band_violations += 1
            logger.warning(f"🚫 BandCap activated: ratio={action_ratio_pct:.1f}% > {upper_limit:.1f}%, "
                          f"blocking injections for {self.config.bandcap_s}s")
        
        band_locked = current_time < self._bandcap_until
        
        # Обчислити dt для інтегратора
        if self.last_update_time is None:
            dt = 1.0  # Перше оновлення
        else:
            dt = current_time - self.last_update_time
            dt = max(0.1, min(dt, 5.0))  # Clamp dt для стабільності
        
        self.last_update_time = current_time
        
        # EWMA фільтрація
        self.ratio_ewma = (self.config.alpha * action_ratio_pct + 
                          (1.0 - self.config.alpha) * self.ratio_ewma)
        
        # Обчислити помилку
        error = self.config.target_pct - self.ratio_ewma
        
        # Інтегральна складова з антивіндап
        self.integral = max(-self.config.integral_max, 
                           min(self.config.integral_max, 
                               self.integral + error * dt))
        
        # PI-контролер
        control_signal = self.config.kp * error + self.config.ki * self.integral
        
        # Перетворити control_signal в prefer_ticks
        # BandCap: якщо активований - блокуємо prefer_ticks
        if band_locked:
            prefer_ticks = 0
            logger.debug(f"🚫 BandCap: prefer_ticks forced to 0 (blocked until {self._bandcap_until - current_time:.1f}s)")
        else:
            prefer_ticks = max(0, min(self.config.prefer_ticks_max, 
                                     int(round(control_signal))))
        
        # Обчислити duty cycle
        duty_cycle = min(self.config.duty_cycle_max, 
                        prefer_ticks / max(1, self.config.prefer_ticks_max))
        
        # Адаптивна noop_penalty
        # Якщо ratio вище цілі (error < 0) - зменшуємо штраф
        # Якщо ratio нижче цілі (error > 0) - збільшуємо штраф
        noop_penalty = (self.config.noop_penalty_base + 
                       self.config.noop_penalty_gain * error / 100.0)
        noop_penalty = max(self.config.noop_penalty_min, 
                          min(self.config.noop_penalty_max, noop_penalty))
        
        # Перевірка допуску
        in_tolerance = abs(error) <= self.config.tolerance_pct
        
        # Зберегти метрики
        metrics = {
            'timestamp': current_time,
            'action_ratio_raw': action_ratio_pct,
            'action_ratio_ewma': self.ratio_ewma,
            'error': error,
            'integral': self.integral,
            'control_signal': control_signal,
            'prefer_ticks': prefer_ticks,
            'duty_cycle': duty_cycle,
            'noop_penalty': noop_penalty,
            'in_tolerance': in_tolerance,
            'band_locked': band_locked,
            'band_violations': self.band_violations
        }
        self.metrics_history.append(metrics)
        
        # Логування (періодичне)
        if len(self.metrics_history) % 10 == 1:  # Кожні ~10 оновлень
            band_status = f" 🚫BAND" if band_locked else ""
            logger.info(f"🎛️ GOVERNOR: ratio={action_ratio_pct:.1f}%→{self.ratio_ewma:.1f}% "
                       f"error={error:+.1f}% prefer_ticks={prefer_ticks} "
                       f"penalty={noop_penalty:.3f}{band_status} {'✅' if in_tolerance else '⚠️'}")
        
        return {
            'prefer_ticks': prefer_ticks,
            'noop_penalty': noop_penalty,
            'duty_cycle': duty_cycle,
            'in_tolerance': in_tolerance,
            'error': error,
            'ratio_ewma': self.ratio_ewma,
            'band_locked': band_locked,
            'band_violations': self.band_violations,
            'metrics': metrics
        }
    
    def register_action_usage(self, action_name: str, timestamp: Optional[float] = None):
        """
        Зареєструвати використання дії для антиспам квот
        
        Args:
            action_name: Назва дії
            timestamp: Час використання
        """
        current_time = timestamp or time.time()
        
        # Оновити usage counts для 60s window
        self.usage_counts_60s[action_name].append(current_time)
        
        # Очистити старі записи (>60s)
        cutoff_time = current_time - 60.0
        while (self.usage_counts_60s[action_name] and 
               self.usage_counts_60s[action_name][0] < cutoff_time):
            self.usage_counts_60s[action_name].popleft()
        
        # Оновити last_used для cooldown
        self.action_last_used[action_name] = current_time
        
        # Зареєструвати injection для квот
        if action_name != 'no_op':
            self.injection_timestamps.append(current_time)
    
    def can_execute_action(self, action_name: str, timestamp: Optional[float] = None) -> tuple[bool, str]:
        """
        Перевірити чи можна виконати дію з урахуванням квот
        
        Args:
            action_name: Назва дії
            timestamp: Поточний час
            
        Returns:
            (can_execute, reason) - чи можна виконати та причина блокування
        """
        current_time = timestamp or time.time()
        
        # Перевірити cooldown для дії
        if action_name in self.action_last_used:
            time_since_last = current_time - self.action_last_used[action_name]
            if time_since_last < self.config.action_cooldown_s:
                return False, f"cooldown_{time_since_last:.1f}s"
        
        # Перевірити квоту на injections per minute
        cutoff_time = current_time - 60.0
        recent_injections = sum(1 for ts in self.injection_timestamps if ts >= cutoff_time)
        
        if recent_injections >= self.config.max_injections_per_min:
            return False, f"quota_{recent_injections}/{self.config.max_injections_per_min}_per_min"
        
        return True, "ok"
    
    def get_action_usage_count(self, action_name: str, window_s: float = 60.0) -> int:
        """Отримати кількість використань дії за вказаний період"""
        current_time = time.time()
        cutoff_time = current_time - window_s
        
        if action_name not in self.usage_counts_60s:
            return 0
            
        return sum(1 for ts in self.usage_counts_60s[action_name] if ts >= cutoff_time)
    
    def get_usage_degradation_penalty(self, action_name: str, lambda_factor: float = 0.03) -> float:
        """
        Обчислити штраф за часте використання дії
        
        Args:
            action_name: Назва дії
            lambda_factor: Коефіцієнт деградації (зазвичай 0.03)
            
        Returns:
            Штраф для віднімання від score дії
        """
        usage_count = self.get_action_usage_count(action_name, window_s=60.0)
        return lambda_factor * usage_count
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Отримати поточний статус Governor для логування"""
        if not self.metrics_history:
            return {"status": "not_initialized"}
        
        latest = self.metrics_history[-1]
        current_time = time.time()
        
        # Обчислити статистику injection rate
        cutoff_time = current_time - 60.0
        recent_injections = sum(1 for ts in self.injection_timestamps if ts >= cutoff_time)
        
        # Топ використовуваних дій
        action_usage = {action: self.get_action_usage_count(action) 
                       for action in self.usage_counts_60s.keys()}
        
        return {
            'status': 'active',
            'target_pct': self.config.target_pct,
            'current_ratio_ewma': latest['action_ratio_ewma'],
            'error': latest['error'],
            'in_tolerance': latest['in_tolerance'],
            'prefer_ticks': latest['prefer_ticks'],
            'duty_cycle': latest['duty_cycle'],
            'noop_penalty': latest['noop_penalty'],
            'injections_per_min': recent_injections,
            'quota_limit': self.config.max_injections_per_min,
            'action_usage_60s': action_usage,
            'last_update': latest['timestamp']
        }