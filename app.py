"""
Albion Online Fishing QTE Assistant
Main Application with Tkinter Dark GUI, real-time visual gauge, and global hotkeys.
"""

import os
import sys
import time
import json
import random
import threading
import ctypes
import cv2
import numpy as np

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from capture import ScreenGrabber
from detector import FishingDetector
from controller import MouseController

# Virtual Key Codes for GetAsyncKeyState
VK_F5 = 0x74
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F10 = 0x79
VK_ESCAPE = 0x1B

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
TEMPLATE_PATH = os.path.join(ASSETS_DIR, "bobber_head.png")


def load_config():
    default_config = {
        "invert_controls": False,
        "min_pct": 42.0,
        "max_pct": 76.0,
        "roi_width": 800,
        "roi_height": 600,
        "humanize": True,
        "poll_interval_sec": 0.015,
        "catches": 0
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_config.update(data)
        except Exception:
            pass
    return default_config


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class FishingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Albion Fishing QTE Assistant v1.0")
        self.root.geometry("620x720")
        self.root.minsize(580, 680)
        self.root.configure(bg="#1A1C23")

        self.cfg = load_config()
        self.is_running = False
        self.minigame_active = False
        self.catches_count = self.cfg.get("catches", 0)

        # Vision & Controller components
        templ = TEMPLATE_PATH if os.path.exists(TEMPLATE_PATH) else None
        self.detector = FishingDetector(templ_path=templ)
        self.grabber = ScreenGrabber(
            roi_width=self.cfg.get("roi_width", 800),
            roi_height=self.cfg.get("roi_height", 600)
        )
        self.controller = MouseController(
            invert_controls=self.cfg.get("invert_controls", False),
            min_pct=self.cfg.get("min_pct", 42.0),
            max_pct=self.cfg.get("max_pct", 76.0),
            humanize=self.cfg.get("humanize", True)
        )

        # Worker thread
        self.worker_thread = None
        self.hotkey_thread = None
        self.stop_signal = threading.Event()

        # Telemetry
        self.current_pct = 50.0
        self.current_action = "IDLE"
        self.current_fps = 0.0

        self._build_ui()
        self._start_hotkey_listener()
        self._poll_ui_telemetry()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        # Header Frame
        header = tk.Frame(self.root, bg="#21252F", pady=12)
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text="🎣 ALBION FISHING QTE HELPER",
            font=("Segoe UI", 16, "bold"),
            fg="#61AFEF",
            bg="#21252F"
        )
        title.pack()

        subtitle = tk.Label(
            header,
            text="Автоматическое удержание поплавка в зеленой зоне",
            font=("Segoe UI", 10),
            fg="#ABB2BF",
            bg="#21252F"
        )
        subtitle.pack()

        # Status Card
        status_card = tk.Frame(self.root, bg="#282C34", padx=16, pady=12, relief=tk.RIDGE, bd=1)
        status_card.pack(fill=tk.X, padx=16, pady=12)

        self.lbl_main_status = tk.Label(
            status_card,
            text="⚪ СТАТУС: ВЫКЛЮЧЕН (Нажмите F5 для старта)",
            font=("Segoe UI", 12, "bold"),
            fg="#E06C75",
            bg="#282C34"
        )
        self.lbl_main_status.pack(pady=4)

        self.lbl_mouse_action = tk.Label(
            status_card,
            text="Мышь: ОТПУЩЕНА (Ожидание поклёвки)",
            font=("Consolas", 11),
            fg="#98C379",
            bg="#282C34"
        )
        self.lbl_mouse_action.pack(pady=2)

        # Visual Gauge (Canvas)
        gauge_frame = tk.Frame(self.root, bg="#1A1C23", padx=16)
        gauge_frame.pack(fill=tk.X, pady=6)

        tk.Label(
            gauge_frame,
            text="Индикатор положения поплавка (Live Gauge):",
            font=("Segoe UI", 10, "bold"),
            fg="#ABB2BF",
            bg="#1A1C23"
        ).pack(anchor=tk.W)

        self.canvas_w = 560
        self.canvas_h = 60
        self.gauge = tk.Canvas(
            gauge_frame,
            width=self.canvas_w,
            height=self.canvas_h,
            bg="#1E222B",
            highlightthickness=1,
            highlightbackground="#3E4451"
        )
        self.gauge.pack(fill=tk.X, pady=6)

        self.lbl_pct = tk.Label(
            gauge_frame,
            text="Поплавок: 0.0%  |  Безопасная зона: 15% - 85%",
            font=("Segoe UI", 9),
            fg="#5C6370",
            bg="#1A1C23"
        )
        self.lbl_pct.pack()

        # Settings Card
        settings_card = tk.LabelFrame(
            self.root,
            text="⚙️ Настройки и механика управления",
            font=("Segoe UI", 11, "bold"),
            fg="#E5C07B",
            bg="#21252F",
            padx=14,
            pady=10
        )
        settings_card.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # Control Mode Toggle
        tk.Label(
            settings_card,
            text="Режим управления:",
            font=("Segoe UI", 10, "bold"),
            fg="#DCDFE4",
            bg="#21252F"
        ).pack(anchor=tk.W, pady=(2, 2))

        self.var_invert = tk.BooleanVar(value=self.cfg.get("invert_controls", False))

        rb_std = tk.Radiobutton(
            settings_card,
            text="Стандарт Albion Online (Зажатие ЛКМ тянет вправо, отпускание — влево)",
            variable=self.var_invert,
            value=False,
            command=self._on_settings_change,
            fg="#98C379",
            bg="#21252F",
            activebackground="#21252F",
            activeforeground="#98C379",
            selectcolor="#282C34"
        )
        rb_std.pack(anchor=tk.W)

        rb_inv = tk.Radiobutton(
            settings_card,
            text="Инверсия (Зажатие ЛКМ тянет влево, отпускание — вправо)",
            variable=self.var_invert,
            value=True,
            command=self._on_settings_change,
            fg="#E5C07B",
            bg="#21252F",
            activebackground="#21252F",
            activeforeground="#E5C07B",
            selectcolor="#282C34"
        )
        rb_inv.pack(anchor=tk.W)

        # Sliders for Thresholds
        slider_frame = tk.Frame(settings_card, bg="#21252F")
        slider_frame.pack(fill=tk.X, pady=8)

        # Min Pct
        tk.Label(
            slider_frame,
            text="Нижний порог зажатия ЛКМ (%):",
            font=("Segoe UI", 9),
            fg="#ABB2BF",
            bg="#21252F"
        ).grid(row=0, column=0, sticky=tk.W)
        self.slider_min = tk.Scale(
            slider_frame,
            from_=20,
            to=60,
            orient=tk.HORIZONTAL,
            bg="#21252F",
            fg="#61AFEF",
            highlightthickness=0,
            command=lambda v: self._on_settings_change()
        )
        self.slider_min.set(int(self.cfg.get("min_pct", 42)))
        self.slider_min.grid(row=0, column=1, sticky=tk.EW, padx=8)

        # Max Pct
        tk.Label(
            slider_frame,
            text="Верхний порог отпускания ЛКМ (%):",
            font=("Segoe UI", 9),
            fg="#ABB2BF",
            bg="#21252F"
        ).grid(row=1, column=0, sticky=tk.W)
        self.slider_max = tk.Scale(
            slider_frame,
            from_=60,
            to=90,
            orient=tk.HORIZONTAL,
            bg="#21252F",
            fg="#E06C75",
            highlightthickness=0,
            command=lambda v: self._on_settings_change()
        )
        self.slider_max.set(int(self.cfg.get("max_pct", 76)))
        self.slider_max.grid(row=1, column=1, sticky=tk.EW, padx=8)
        slider_frame.columnconfigure(1, weight=1)

        # Humanize Jitter Checkbox
        self.var_humanize = tk.BooleanVar(value=self.cfg.get("humanize", True))
        chk_humanize = tk.Checkbutton(
            settings_card,
            text="Человеческий фактор (рандомизация микро-задержек для защиты от античита)",
            variable=self.var_humanize,
            command=self._on_settings_change,
            fg="#ABB2BF",
            bg="#21252F",
            activebackground="#21252F",
            activeforeground="#ABB2BF",
            selectcolor="#282C34"
        )
        chk_humanize.pack(anchor=tk.W, pady=4)

        # Hotkeys & Controls Panel
        btn_frame = tk.Frame(self.root, bg="#1A1C23", padx=16, pady=8)
        btn_frame.pack(fill=tk.X)

        self.btn_toggle = tk.Button(
            btn_frame,
            text="▶ ЗАПУСК (F5)",
            font=("Segoe UI", 11, "bold"),
            bg="#98C379",
            fg="#1E222B",
            activebackground="#78A55B",
            padx=16,
            pady=8,
            command=self.toggle_running
        )
        self.btn_toggle.pack(side=tk.LEFT, padx=4)

        btn_test = tk.Button(
            btn_frame,
            text="📸 Тест детекции (F8)",
            font=("Segoe UI", 10),
            bg="#3E4451",
            fg="#DCDFE4",
            activebackground="#4B5263",
            padx=12,
            pady=8,
            command=self.run_test_screenshot
        )
        btn_test.pack(side=tk.LEFT, padx=4)

        btn_help = tk.Button(
            btn_frame,
            text="❓ Справка",
            font=("Segoe UI", 10),
            bg="#3E4451",
            fg="#DCDFE4",
            activebackground="#4B5263",
            padx=12,
            pady=8,
            command=self.show_help
        )
        btn_help.pack(side=tk.RIGHT, padx=4)

        # Footer Stats
        footer = tk.Frame(self.root, bg="#181A1F", padx=16, pady=6)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_stats = tk.Label(
            footer,
            text=f"Выловлено: {self.catches_count}  |  FPS: 0  |  F5: Старт/Пауза  |  F7: Режим  |  F10: Стоп",
            font=("Segoe UI", 9),
            fg="#5C6370",
            bg="#181A1F"
        )
        self.lbl_stats.pack(anchor=tk.W)

    def _draw_gauge(self, pct, is_active, is_holding):
        self.gauge.delete("all")
        w = self.canvas_w
        h = self.canvas_h
        y_top = 12
        y_bot = 40

        # Bar zones:
        # Left danger (0% to 15%)
        x_left_red = int(w * 0.15)
        # Right danger (85% to 100%)
        x_right_red = int(w * 0.85)

        # Danger Left (Orange/Red)
        self.gauge.create_rectangle(0, y_top, x_left_red, y_bot, fill="#D16947", outline="")
        # Safe Green (15% to 85%)
        self.gauge.create_rectangle(x_left_red, y_top, x_right_red, y_bot, fill="#396D1C", outline="")
        # Danger Right (Orange/Red)
        self.gauge.create_rectangle(x_right_red, y_top, w, y_bot, fill="#D16947", outline="")

        # Target thresholds lines:
        x_min_line = int(w * (self.slider_min.get() / 100.0))
        x_max_line = int(w * (self.slider_max.get() / 100.0))
        self.gauge.create_line(x_min_line, y_top, x_min_line, y_bot, fill="#61AFEF", width=2, dash=(3, 2))
        self.gauge.create_line(x_max_line, y_top, x_max_line, y_bot, fill="#E06C75", width=2, dash=(3, 2))

        # Bobber marker:
        if is_active and pct is not None:
            bx = int(w * (pct / 100.0))
            bx = max(8, min(w - 8, bx))
            # Draw pointer arrow and circle
            marker_color = "#E5C07B" if not is_holding else "#98C379"
            self.gauge.create_polygon(bx - 6, y_top - 8, bx + 6, y_top - 8, bx, y_top, fill=marker_color)
            self.gauge.create_oval(bx - 6, y_top + 4, bx + 6, y_bot - 4, fill="#FFFFFF", outline="#E06C75", width=2)
            self.gauge.create_polygon(bx - 6, y_bot + 8, bx + 6, y_bot + 8, bx, y_bot, fill=marker_color)
        else:
            # Idle dashed center
            cx = w // 2
            self.gauge.create_text(cx, (y_top + y_bot) // 2, text="ОЖИДАНИЕ МИНИ-ИГРЫ", fill="#ABB2BF", font=("Segoe UI", 9, "bold"))

    def _on_settings_change(self):
        self.cfg["invert_controls"] = self.var_invert.get()
        self.cfg["min_pct"] = float(self.slider_min.get())
        self.cfg["max_pct"] = float(self.slider_max.get())
        self.cfg["humanize"] = self.var_humanize.get()
        self.controller.invert_controls = self.cfg["invert_controls"]
        self.controller.min_pct = self.cfg["min_pct"]
        self.controller.max_pct = self.cfg["max_pct"]
        self.controller.humanize = self.cfg["humanize"]
        save_config(self.cfg)

    def toggle_running(self):
        if not self.is_running:
            self.start_worker()
        else:
            self.stop_worker()

    def start_worker(self):
        self.is_running = True
        self.stop_signal.clear()
        self.btn_toggle.configure(text="⏸ ПАУЗА (F5)", bg="#E06C75")
        self.lbl_main_status.configure(text="🟢 АКТИВЕН: Ожидание поклёвки...", fg="#98C379")
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def stop_worker(self):
        self.is_running = False
        self.stop_signal.set()
        self.controller.emergency_release()
        self.btn_toggle.configure(text="▶ ЗАПУСК (F5)", bg="#98C379")
        self.lbl_main_status.configure(text="⚪ СТАТУС: НА ПАУЗЕ (Нажмите F5)", fg="#E06C75")
        self.lbl_mouse_action.configure(text="Мышь: ОТПУЩЕНА", fg="#ABB2BF")

    def _worker_loop(self):
        poll_sec = self.cfg.get("poll_interval_sec", 0.015)
        frames = 0
        fps_timer = time.time()
        was_active = False

        while self.is_running and not self.stop_signal.is_set():
            t0 = time.perf_counter()
            try:
                frame = self.grabber.grab_roi()
                res = self.detector.detect(frame)
            except Exception as e:
                time.sleep(0.05)
                continue

            if res and res.get("active"):
                self.minigame_active = True
                pct = res.get("bobber_pct")
                self.current_pct = pct

                action = self.controller.update(pct)
                self.current_action = action
                was_active = True
            else:
                if was_active:
                    # Minigame just ended! (Fish caught or escaped)
                    self.controller.emergency_release()
                    self.catches_count += 1
                    self.cfg["catches"] = self.catches_count
                    save_config(self.cfg)
                    was_active = False

                self.minigame_active = False
                self.controller.release()
                self.current_action = "IDLE"

            frames += 1
            if time.time() - fps_timer >= 1.0:
                self.current_fps = frames / (time.time() - fps_timer)
                frames = 0
                fps_timer = time.time()

            elapsed = time.perf_counter() - t0
            sleep_time = max(0.001, poll_sec - elapsed)
            time.sleep(sleep_time)

        self.controller.emergency_release()

    def _start_hotkey_listener(self):
        def hotkey_loop():
            user32 = ctypes.windll.user32
            last_press = {}

            def is_key_just_pressed(vk, cooldown=0.3):
                state = user32.GetAsyncKeyState(vk)
                # High-order bit indicates key is down
                if state & 0x8000:
                    now = time.time()
                    if now - last_press.get(vk, 0) > cooldown:
                        last_press[vk] = now
                        return True
                return False

            while not self.stop_signal.is_set():
                if is_key_just_pressed(VK_F5):
                    self.root.after(0, self.toggle_running)
                elif is_key_just_pressed(VK_F7):
                    # Toggle inverted
                    new_val = not self.var_invert.get()
                    self.root.after(0, lambda: self.var_invert.set(new_val))
                    self.root.after(0, self._on_settings_change)
                elif is_key_just_pressed(VK_F8):
                    self.root.after(0, self.run_test_screenshot)
                elif is_key_just_pressed(VK_F10) or is_key_just_pressed(VK_ESCAPE):
                    self.root.after(0, self.stop_worker)
                time.sleep(0.03)

        self.hotkey_thread = threading.Thread(target=hotkey_loop, daemon=True)
        self.hotkey_thread.start()

    def _poll_ui_telemetry(self):
        # Update live visual gauge
        if self.minigame_active:
            holding = self.controller.is_holding
            action_text = "🟡 ЛКМ ЗАЖАТА (Тянем)" if holding else "⚪ ЛКМ ОТПУЩЕНА (Даем слабину)"
            fg_color = "#E5C07B" if holding else "#98C379"
            self.lbl_main_status.configure(text="🎣 МИНИ-ИГРА ИДЁТ!", fg="#61AFEF")
            self.lbl_mouse_action.configure(text=f"Мышь: {action_text}", fg=fg_color)
            if self.current_pct is not None:
                self.lbl_pct.configure(text=f"Поплавок: {self.current_pct:.1f}%  |  Зона: {self.slider_min.get()}% - {self.slider_max.get()}%")
            self._draw_gauge(self.current_pct, True, holding)
        else:
            if self.is_running:
                self.lbl_main_status.configure(text="🟢 АКТИВЕН: Ожидание поклёвки...", fg="#98C379")
                self.lbl_mouse_action.configure(text="Мышь: Ожидание рыбы", fg="#ABB2BF")
            self._draw_gauge(50.0, False, False)

        # Update stats
        inv_label = "Инверсия" if self.var_invert.get() else "Стандарт"
        self.lbl_stats.configure(
            text=f"Выловлено: {self.catches_count}  |  FPS: {self.current_fps:.0f}  |  Режим: {inv_label}  |  F5: Старт/Пауза  |  F7: Режим  |  F8: Тест"
        )

        self.root.after(35, self._poll_ui_telemetry)

    def run_test_screenshot(self):
        """Captures a test screenshot and displays detection overlay."""
        try:
            frame = self.grabber.grab_roi()
            res = self.detector.detect(frame)
            dbg = frame.copy()

            if res and res.get("active"):
                bx, by, bw, bh = res["bar_rect"]
                cv2.rectangle(dbg, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
                bobber_x = res.get("bobber_x")
                if bobber_x is not None:
                    abs_bx = int(bx + bobber_x)
                    cv2.line(dbg, (abs_bx, by - 15), (abs_bx, by + bh + 15), (0, 0, 255), 2)
                    cv2.circle(dbg, (abs_bx, by + bh // 2), 6, (0, 255, 255), -1)
                info = f"Found! Bobber: {res['bobber_pct']:.1f}% via {res['method']}"
                cv2.putText(dbg, info, (bx, max(25, by - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(dbg, "Minigame not found in ROI", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            dbg_path = os.path.join(os.path.dirname(__file__), "test_calibration.png")
            cv2.imwrite(dbg_path, dbg)

            # Show dialog
            if res and res.get("active"):
                messagebox.showinfo(
                    "Тест детекции (F8)",
                    f"✅ Мини-игра успешно обнаружена!\n\n"
                    f"Положение поплавка: {res['bobber_pct']:.1f}%\n"
                    f"Метод: {res['method']}\n"
                    f"Координаты: {res['bar_rect']}\n\n"
                    f"Снимок сохранён в test_calibration.png"
                )
            else:
                messagebox.showwarning(
                    "Тест детекции (F8)",
                    "⚠️ Мини-игра не обнаружена в центральной области экрана.\n\n"
                    "Убедитесь, что мини-игра активна на экране или проверьте масштаб UI в игре."
                )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось выполнить тест детекции:\n{e}")

    def show_help(self):
        help_text = (
            "📖 СПРАВКА ПО РАБОТЕ С ПРОГРАММОЙ\n\n"
            "1. Забросьте удочку в игре Albion Online.\n"
            "2. Когда рыба клюнет — нажмите ЛКМ для начала мини-игры.\n"
            "3. Ассистент автоматически обнаружит появление зелёной шкалы и начнёт управлять поплавком.\n\n"
            "ГОРЯЧИЕ КЛАВИШИ:\n"
            "• F5 — Запуск / Приостановка бота\n"
            "• F7 — Переключить режим управления (Стандарт / Инверсия)\n"
            "• F8 — Тестовый снимок (проверка распознавания)\n"
            "• F10 или Esc — Экстренная остановка\n\n"
            "РЕЖИМЫ УПРАВЛЕНИЯ:\n"
            "• Стандарт Albion: Зажатие ЛКМ тянет вправо (подсечка), отпускание — поплавок плывет влево.\n"
            "• Инверсия: Зажатие ЛКМ тянет влево, отпускание — вправо."
        )
        messagebox.showinfo("Справка", help_text)

    def on_close(self):
        self.stop_signal.set()
        self.controller.emergency_release()
        self.grabber.close()
        self.root.destroy()
        sys.exit(0)


if __name__ == "__main__":
    root = tk.Tk()
    app = FishingApp(root)
    root.mainloop()
