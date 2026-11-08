"""
Albion Online Fishing QTE Bot (Zero-NN Color Masking + Hysteresis)
Pure Python + OpenCV / NumPy implementation.
"""

import os
import sys
import time
import ctypes
import numpy as np
import cv2
import mss

# Windows API constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_F5 = 0x74
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F10 = 0x79
VK_ESCAPE = 0x1B


class FastQTEBot:
    def __init__(
        self,
        hold_pulls_left=True,   # По условию пользователя: удержание ЛКМ тянет поплавок влево
        roi_width=240,
        roi_height=40,
        min_pct=None,           # Нижний порог от 0 до 100%
        max_pct=None,           # Верхний порог от 0 до 100%
        target_fps=90
    ):
        self.hold_pulls_left = hold_pulls_left
        self.roi_width = roi_width
        self.roi_height = roi_height
        self.target_fps = target_fps
        self.poll_interval = 1.0 / target_fps

        # Загрузка порогов из config.json при наличии
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        cfg = {}
        if os.path.exists(cfg_path):
            try:
                import json
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                pass

        if min_pct is None:
            min_pct = cfg.get("min_pct", 42.0)
        if max_pct is None:
            max_pct = cfg.get("max_pct", 76.0)

        # Пороги от 0 до 100%
        self.min_pct = max(0.0, min(100.0, float(min_pct)))
        self.max_pct = max(0.0, min(100.0, float(max_pct)))

        # Быстрое удержание и человеческий фактор
        self.rapid_mode = cfg.get("rapid_mode", True)
        self.pulse_ms = cfg.get("pulse_ms", 60)
        self.humanize_ms = cfg.get("humanize_ms", 20)
        self.last_pulse_toggle = 0.0
        self.current_pulse_duration = self.pulse_ms / 1000.0

        self.user32 = ctypes.windll.user32
        self._attach_desktop()

        self.sct = mss.MSS()
        self.primary_mon = self.sct.monitors[1]
        self.screen_w = self.primary_mon["width"]
        self.screen_h = self.primary_mon["height"]

        # Default ROI in screen center:
        self.roi = {
            "left": (self.screen_w - self.roi_width) // 2,
            "top": (self.screen_h - self.roi_height) // 2 - 40,
            "width": self.roi_width,
            "height": self.roi_height
        }

        # Вычисление порогов в пикселях (0 .. roi_width)
        self.left_threshold = (self.min_pct / 100.0) * self.roi_width
        self.right_threshold = (self.max_pct / 100.0) * self.roi_width
        self.center_x = (self.left_threshold + self.right_threshold) / 2.0

        self.is_holding = False
        self.is_active = False

    def _attach_desktop(self):
        try:
            hdesk = self.user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                self.user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    def mouse_down(self):
        if not self.is_holding:
            if self.humanize_ms > 0:
                import random
                time.sleep(random.uniform(self.humanize_ms * 0.4, self.humanize_ms * 1.4) / 1000.0)
            self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.is_holding = True

    def mouse_up(self):
        if self.is_holding:
            if self.humanize_ms > 0:
                import random
                time.sleep(random.uniform(self.humanize_ms * 0.3, self.humanize_ms * 1.2) / 1000.0)
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_holding = False

    def _fast_toggle(self):
        """Быстрое переключение для удержания поплавка микро-кликами"""
        import random
        now = time.time()
        if now - self.last_pulse_toggle >= self.current_pulse_duration:
            self.last_pulse_toggle = now
            base_s = self.pulse_ms / 1000.0
            jitter_s = (self.humanize_ms * 0.0003) if self.humanize_ms > 0 else 0
            self.current_pulse_duration = max(0.025, base_s + random.uniform(-jitter_s, jitter_s))

            if self.is_holding:
                self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                self.is_holding = False
            else:
                self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                self.is_holding = True

    def emergency_release(self):
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self.is_holding = False

    def auto_calibrate_roi(self):
        """
        Scans central 800x600 region to automatically locate the minigame bar
        and center the 240x40 ROI directly on it.
        """
        scan_w, scan_h = 800, 600
        scan_box = {
            "left": max(0, (self.screen_w - scan_w) // 2),
            "top": max(0, (self.screen_h - scan_h) // 2),
            "width": scan_w,
            "height": scan_h
        }
        frame = np.array(self.sct.grab(scan_box))[:, :, :3]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Look for green tension bar
        green_mask = cv2.inRange(hsv, (38, 80, 50), (65, 255, 170))
        proj_y = green_mask.sum(axis=1)
        green_rows = np.where(proj_y > 255 * 40)[0]

        if len(green_rows) > 0:
            y_min, y_max = green_rows.min(), green_rows.max()
            bar_slice = green_mask[y_min:y_max + 1, :]
            proj_x = bar_slice.sum(axis=0)
            green_cols = np.where(proj_x > 0)[0]
            if len(green_cols) > 0:
                x_center = int(scan_box["left"] + np.median(green_cols))
                y_center = int(scan_box["top"] + (y_min + y_max) // 2)

                self.roi["left"] = max(0, x_center - self.roi_width // 2)
                self.roi["top"] = max(0, y_center - self.roi_height // 2)
                print(f"[+] Авто-калибровка успешна! Полоса найдена в: ({self.roi['left']}, {self.roi['top']})")
                return True

        print("[-] Авто-калибровка: зелёная полоса пока не видна (используются координаты центра экрана).")
        return False

    def find_bobber_x(self, roi_bgr):
        """
        Fast Color Masking algorithm (< 0.05 ms):
        Finds the bobber's white body (R > 200, G > 200, B > 180).
        Returns bobber_x (float) or None.
        """
        # White pixels inside the bar
        white_mask = (roi_bgr[:, :, 2] > 200) & (roi_bgr[:, :, 1] > 200) & (roi_bgr[:, :, 0] > 180)
        ys, xs = np.where(white_mask)
        if len(xs) >= 4:
            return float(np.mean(xs))

        # Fallback: Orange / Red feathers (R > 190, G in 90..180, B < 60)
        orange_mask = (roi_bgr[:, :, 2] > 190) & (roi_bgr[:, :, 1] > 90) & \
                      (roi_bgr[:, :, 1] < 180) & (roi_bgr[:, :, 0] < 60)
        oys, oxs = np.where(orange_mask)
        if len(oxs) >= 8:
            return float(np.median(oxs))

        return None

    def update_hysteresis(self, bobber_x):
        """
        Hysteresis / Deadzone Logic:
        Prevents rapid click-spamming by creating a stable deadzone corridor around center_x.
        """
        if bobber_x is None:
            # Bobber lost / minigame inactive -> safety release
            self.mouse_up()
            return "IDLE"

        if self.hold_pulls_left:
            # === Пользовательская модель ===
            # Зажатие ЛКМ тянет поплавок ВЛЕВО.
            # Отпускание ЛКМ позволяет поплавку дрейфовать ВПРАВО.
            if bobber_x > self.right_threshold:
                # Поплавок уходит слишком вправо -> ЗАЖИМАЕМ ЛКМ, чтобы потянуть влево
                self.mouse_down()
                return "PULL_LEFT (DOWN)"
            elif bobber_x < self.left_threshold:
                # Поплавок дошёл до левой границы -> ОТПУСКАЕМ ЛКМ, чтобы не ушёл в левую красную зону
                self.mouse_up()
                return "DRIFT_RIGHT (UP)"
            else:
                # Внутри диапазона [left_threshold, right_threshold]
                if self.rapid_mode:
                    self._fast_toggle()
                    return "RAPID_PULSE (HOLD)" if self.is_holding else "RAPID_PULSE (SLACK)"
                else:
                    return "IN_CORRIDOR (HOLDING)" if self.is_holding else "IN_CORRIDOR (COASTING)"
        else:
            # === Стандартная физика Albion ===
            # Зажатие ЛКМ подтягивает рыбу и тянет поплавок ВПРАВО.
            # Отпускание ЛКМ даёт слабину и поплавок плывёт ВЛЕВО.
            if bobber_x > self.right_threshold:
                # Слишком близко к правому краю -> ОТПУСКАЕМ ЛКМ
                self.mouse_up()
                return "SLACK_LEFT (UP)"
            elif bobber_x < self.left_threshold:
                # Поплавок опустился влево -> ЗАЖИМАЕМ ЛКМ
                self.mouse_down()
                return "REEL_RIGHT (DOWN)"
            else:
                if self.rapid_mode:
                    self._fast_toggle()
                    return "RAPID_PULSE (HOLD)" if self.is_holding else "RAPID_PULSE (SLACK)"
                else:
                    return "IN_CORRIDOR (HOLDING)" if self.is_holding else "IN_CORRIDOR (COASTING)"

    def render_ascii_gauge(self, bobber_x):
        """Draws visual ASCII gauge in terminal."""
        width = 30
        if bobber_x is None:
            return "[" + " " * width + "] Ожидание поклёвки..."

        rel = max(0.0, min(1.0, bobber_x / max(1, self.roi_width)))
        pos = int(rel * (width - 1))

        # Deadzone bracket positions
        d_left = int((self.left_threshold / self.roi_width) * (width - 1))
        d_right = int((self.right_threshold / self.roi_width) * (width - 1))

        chars = ["-"] * width
        for i in range(d_left, d_right + 1):
            chars[i] = "="
        chars[pos] = "*" if not self.is_holding else "@"

        status = "ЛКМ [ЗАЖАТА]" if self.is_holding else "ЛКМ [ОТПУЩЕНА]"
        return f"[{''.join(chars)}] X={bobber_x:5.1f}px | {status}"

    def run(self):
        print("=" * 65)
        print("🎣  ALBION ONLINE — QTE COLOR MASKING & HYSTERESIS BOT")
        print("=" * 65)
        print(f"Экран: {self.screen_w}x{self.screen_h}")
        print(f"Область захвата (ROI): {self.roi_width}x{self.roi_height} в ({self.roi['left']}, {self.roi['top']})")
        print(f"Пороги удержания: {self.min_pct:.0f}% ... {self.max_pct:.0f}% ({self.left_threshold:.0f}px ... {self.right_threshold:.0f}px)")
        mode_str = "Зажатие ЛКМ тянет ВЛЕВО" if self.hold_pulls_left else "Стандарт Albion (Зажатие тянет ВПРАВО)"
        print(f"Режим управления: {mode_str}")
        print("-" * 65)
        print("ГОРЯЧИЕ КЛАВИШИ:")
        print("  [F5]  — Запуск / Пауза")
        print("  [F6]  — Быстрое удержание (ВКЛ / ВЫКЛ микро-клики)")
        print("  [F7]  — Переключить направление (Зажатие влево / вправо)")
        print("  [F8]  — Авто-калибровка координат полосы")
        print("  [Esc] или [F10] — Выход")
        print("=" * 65)

        self.is_active = False
        last_key_press = {}

        def key_down(vk, cooldown=0.3):
            if self.user32.GetAsyncKeyState(vk) & 0x8000:
                now = time.time()
                if now - last_key_press.get(vk, 0) > cooldown:
                    last_key_press[vk] = now
                    return True
            return False

        try:
            while True:
                # Hotkey polling
                if key_down(VK_F5):
                    self.is_active = not self.is_active
                    if not self.is_active:
                        self.emergency_release()
                        print("\n⏸  [ПАУЗА] Бот временно приостановлен.")
                    else:
                        print("\n▶  [СТАРТ] Бот АКТИВЕН и отслеживает поплавок!")

                if key_down(VK_F6):
                    self.rapid_mode = not self.rapid_mode
                    status = "ВКЛ (микро-клики)" if self.rapid_mode else "ВЫКЛ (обычный)"
                    print(f"\n⚡  [БЫСТРОЕ УДЕРЖАНИЕ]: {status}")

                if key_down(VK_F7):
                    self.hold_pulls_left = not self.hold_pulls_left
                    mode_name = "Зажатие ЛКМ тянет ВЛЕВО" if self.hold_pulls_left else "Стандарт (Зажатие тянет ВПРАВО)"
                    print(f"\n🔄  [РЕЖИМ СМЕНЕН]: {mode_name}")

                if key_down(VK_F8):
                    print("\n🔍  [КАЛИБРОВКА] Поиск полосы на экране...")
                    self.auto_calibrate_roi()

                if key_down(VK_ESCAPE) or key_down(VK_F10):
                    print("\n🛑  [ВЫХОД] Остановка бота...")
                    break

                if self.is_active:
                    t_start = time.perf_counter()

                    # 1. Захват ROI (< 0.5 мс)
                    frame = np.array(self.sct.grab(self.roi))[:, :, :3]

                    # 2. Поиск X-координаты поплавка через Color Masking (< 0.05 мс)
                    bx = self.find_bobber_x(frame)

                    # 3. Удержание с гистерезисом (защита от дребезга)
                    action = self.update_hysteresis(bx)

                    # 4. Вывод визуального индикатора в одну строку консоли
                    gauge = self.render_ascii_gauge(bx)
                    sys.stdout.write(f"\r{gauge} | {action:22s}")
                    sys.stdout.flush()

                    dt = time.perf_counter() - t_start
                    sleep_time = max(0.001, self.poll_interval - dt)
                    time.sleep(sleep_time)
                else:
                    time.sleep(0.05)

        finally:
            self.emergency_release()
            self.sct.close()
            print("\nСессия завершена.")


if __name__ == "__main__":
    bot = FastQTEBot(hold_pulls_left=True)
    bot.run()
