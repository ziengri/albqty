"""
Albion Online Fishing QTE - Mouse Controller
Handles hardware mouse simulation, safety releases, and hysteresis logic.
"""

import ctypes
import time
import random

# Windows API Mouse constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MouseController:
    def __init__(self, invert_controls=False, min_pct=42.0, max_pct=76.0, humanize=True):
        self.invert_controls = invert_controls
        self.min_pct = min_pct
        self.max_pct = max_pct
        self.humanize = humanize
        self.is_holding = False
        self.last_action_time = 0.0

    def press(self):
        """Simulates Left Mouse Button Down."""
        if not self.is_holding:
            if self.humanize:
                time.sleep(random.uniform(0.005, 0.020))
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.is_holding = True
            self.last_action_time = time.time()

    def release(self):
        """Simulates Left Mouse Button Up."""
        if self.is_holding:
            if self.humanize:
                time.sleep(random.uniform(0.005, 0.015))
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_holding = False
            self.last_action_time = time.time()

    def emergency_release(self):
        """Guaranteed release of mouse button without any delays."""
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self.is_holding = False

    def update(self, bobber_pct):
        """
        Updates controller state based on bobber percentage (0-100%).
        Returns:
            str: current action ("HOLDING", "RELEASED", "MAINTAINING")
        """
        if bobber_pct is None:
            # If bobber lost during minigame, safety release
            self.release()
            return "LOST_RELEASED"

        if not self.invert_controls:
            # Standard Albion physics:
            # Holding LMB -> bobber moves RIGHT (tension increases)
            # Releasing LMB -> bobber drifts LEFT (tension drops)
            if bobber_pct >= self.max_pct:
                self.release()
                return "RELEASED"
            elif bobber_pct <= self.min_pct:
                self.press()
                return "HOLDING"
            else:
                return "HOLDING" if self.is_holding else "RELEASED"
        else:
            # Inverted controls (user phrased: "hold LMB so it goes left"):
            # Holding LMB -> bobber moves LEFT
            # Releasing LMB -> bobber drifts RIGHT
            if bobber_pct >= self.max_pct:
                self.press()
                return "HOLDING"
            elif bobber_pct <= self.min_pct:
                self.release()
                return "RELEASED"
            else:
                return "HOLDING" if self.is_holding else "RELEASED"
