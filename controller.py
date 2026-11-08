"""
Albion Online Fishing QTE - Mouse Controller
Handles hardware mouse simulation, rapid pulsing (PWM holding), and customizable humanization.
"""

import ctypes
import time
import random

# Windows API Mouse constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MouseController:
    def __init__(
        self,
        invert_controls=False,
        min_pct=42.0,
        max_pct=76.0,
        humanize_ms=20,
        rapid_mode=True,
        pulse_ms=60
    ):
        self.invert_controls = invert_controls
        self.min_pct = min_pct
        self.max_pct = max_pct
        self.humanize_ms = humanize_ms
        self.rapid_mode = rapid_mode
        self.pulse_ms = pulse_ms

        self.is_holding = False
        self.last_action_time = 0.0
        self.last_pulse_toggle = 0.0
        self.current_pulse_duration = pulse_ms / 1000.0

    def press(self):
        """Simulates Left Mouse Button Down."""
        if not self.is_holding:
            if self.humanize_ms > 0:
                jitter = random.uniform(self.humanize_ms * 0.4, self.humanize_ms * 1.4) / 1000.0
                time.sleep(jitter)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.is_holding = True
            self.last_action_time = time.time()

    def release(self):
        """Simulates Left Mouse Button Up."""
        if self.is_holding:
            if self.humanize_ms > 0:
                jitter = random.uniform(self.humanize_ms * 0.3, self.humanize_ms * 1.2) / 1000.0
                time.sleep(jitter)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_holding = False
            self.last_action_time = time.time()

    def _fast_toggle(self):
        """Toggles mouse state for rapid pulsing."""
        now = time.time()
        if now - self.last_pulse_toggle >= self.current_pulse_duration:
            self.last_pulse_toggle = now
            # Next duration with slight organic jitter
            base_s = self.pulse_ms / 1000.0
            jitter_s = (self.humanize_ms * 0.0003) if self.humanize_ms > 0 else 0
            self.current_pulse_duration = max(0.025, base_s + random.uniform(-jitter_s, jitter_s))

            if self.is_holding:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                self.is_holding = False
            else:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                self.is_holding = True

    def emergency_release(self):
        """Guaranteed release of mouse button without any delays."""
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self.is_holding = False

    def update(self, bobber_pct):
        """
        Updates controller state based on bobber percentage (0-100%).
        Returns:
            str: current action description
        """
        if bobber_pct is None:
            self.release()
            return "LOST_RELEASED"

        if not self.invert_controls:
            # === Стандарт Albion Online ===
            # Зажатие ЛКМ -> смещение вправо (подсечка)
            # Отпускание ЛКМ -> смещение влево (слабина)
            if bobber_pct >= self.max_pct:
                # Превышен верхний порог -> отпускаем ЛКМ для возврата влево
                self.release()
                return "RELEASED (HIGH)"
            elif bobber_pct <= self.min_pct:
                # Ниже нижнего порога -> зажимаем ЛКМ для возврата вправо
                self.press()
                return "HOLDING (LOW)"
            else:
                # Внутри диапазона [min_pct, max_pct]
                if self.rapid_mode:
                    self._fast_toggle()
                    return "RAPID_PULSE (HOLD)" if self.is_holding else "RAPID_PULSE (SLACK)"
                else:
                    return "IN_RANGE (HOLD)" if self.is_holding else "IN_RANGE (SLACK)"
        else:
            # === Инвертированный режим ===
            # Зажатие ЛКМ -> смещение влево
            # Отпускание ЛКМ -> смещение вправо
            if bobber_pct >= self.max_pct:
                # Превышен верхний порог -> зажимаем ЛКМ, чтобы тянуть влево
                self.press()
                return "HOLDING (PULL_LEFT)"
            elif bobber_pct <= self.min_pct:
                # Ниже нижнего порога -> отпускаем ЛКМ, чтобы дрейфовал вправо
                self.release()
                return "RELEASED (DRIFT_RIGHT)"
            else:
                # Внутри диапазона [min_pct, max_pct]
                if self.rapid_mode:
                    self._fast_toggle()
                    return "RAPID_PULSE (HOLD)" if self.is_holding else "RAPID_PULSE (SLACK)"
                else:
                    return "IN_RANGE (HOLD)" if self.is_holding else "IN_RANGE (SLACK)"
