import json
import threading

import tkinter as tk
from tkinter import ttk

from pynput import keyboard
import pystray
from PIL import Image, ImageDraw

from constants import HOTKEY_OPTIONS, KEY_MAP, SETTINGS_FILE
from engine import VoiceInputEngine
from widget import FloatingWidget


class VoiceInputApp:
    def __init__(self):
        self.engine = VoiceInputEngine(
            on_status_change=self._on_engine_status,
        )
        self.settings = self._load_settings()
        self.listener = None
        self.tray = None
        self._build_gui()
        self._apply_settings_to_gui()
        self.floating = FloatingWidget(self.root, on_double_click=self._show_window)
        self._start_listener()

    def _load_settings(self):
        defaults = {
            "server_url": "ws://localhost:10096",
            "hotkey": "ctrl_r",
            "mode": "continuous",
        }
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return defaults

    def _save_settings(self):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    # ── GUI ──────────────────────────────────────────────

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("语音输入法")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # Server
        ttk.Label(main, text="服务器地址:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.server_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.server_var, width=32).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, pady=4)

        # Hotkey
        ttk.Label(main, text="热键:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.hotkey_var = tk.StringVar()
        ttk.Combobox(main, textvariable=self.hotkey_var,
                     values=list(HOTKEY_OPTIONS.keys()),
                     state="readonly", width=14).grid(
            row=1, column=1, sticky=tk.W, pady=4)

        # Mode
        ttk.Label(main, text="录入模式:").grid(row=2, column=0, sticky=tk.W, pady=4)
        mode_frame = ttk.Frame(main)
        mode_frame.grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=4)
        self.mode_var = tk.StringVar()
        ttk.Radiobutton(mode_frame, text="持续识别", variable=self.mode_var,
                        value="continuous", command=self._update_desc).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Radiobutton(mode_frame, text="按住说话", variable=self.mode_var,
                        value="ptt", command=self._update_desc).pack(side=tk.LEFT)

        # Separator
        ttk.Separator(main, orient=tk.HORIZONTAL).grid(
            row=3, column=0, columnspan=3, sticky=tk.EW, pady=8)

        # Status
        sf = ttk.Frame(main)
        sf.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=4)
        ttk.Label(sf, text="状态:").pack(side=tk.LEFT)
        self.status_dot = tk.Canvas(sf, width=14, height=14, highlightthickness=0,
                                    bg=self.root.cget("bg"))
        self.status_dot.pack(side=tk.LEFT, padx=5)
        self.dot_id = self.status_dot.create_oval(2, 2, 12, 12, fill="gray", outline="")
        self.status_label = ttk.Label(sf, text="就绪")
        self.status_label.pack(side=tk.LEFT)

        # Buttons
        bf = ttk.Frame(main)
        bf.grid(row=5, column=0, columnspan=3, pady=10)
        ttk.Button(bf, text="保存设置", command=self._on_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="最小化到托盘", command=self._minimize_to_tray).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="退出", command=self._quit).pack(side=tk.LEFT, padx=4)

        # Description
        ttk.Separator(main, orient=tk.HORIZONTAL).grid(
            row=6, column=0, columnspan=3, sticky=tk.EW, pady=8)
        self.desc_label = ttk.Label(main, text="", wraplength=320, foreground="gray")
        self.desc_label.grid(row=7, column=0, columnspan=3, sticky=tk.W)

    def _apply_settings_to_gui(self):
        self.server_var.set(self.settings["server_url"])
        for name, key in HOTKEY_OPTIONS.items():
            if key == self.settings["hotkey"]:
                self.hotkey_var.set(name)
                break
        self.mode_var.set(self.settings["mode"])
        self.engine.server_url = self.settings["server_url"]
        self._update_desc()

    def _update_desc(self):
        mode = self.mode_var.get()
        hk = self.hotkey_var.get()
        if mode == "ptt":
            self.desc_label.config(text=f"按住 [{hk}] 录音，松开后自动识别并输入文字")
        else:
            self.desc_label.config(text=f"按 [{hk}] 开始实时识别，再按一次停止")

    def _on_engine_status(self, status):
        try:
            self.root.after(0, lambda: self._update_status_ui(status))
        except Exception:
            pass

    def _update_status_ui(self, status):
        mode = self.settings.get("mode", "continuous")
        if status == "recording":
            self.status_dot.itemconfig(self.dot_id, fill="#E74C3C")
            self.status_label.config(text="录音中...")
        elif status == "识别中...":
            self.status_dot.itemconfig(self.dot_id, fill="#F39C12")
            self.status_label.config(text="识别中...")
        elif status == "idle":
            self.status_dot.itemconfig(self.dot_id, fill="#2ECC71")
            self.status_label.config(text="就绪")
        else:
            self.status_dot.itemconfig(self.dot_id, fill="#E74C3C")
            self.status_label.config(text=str(status))
        self.floating.update(status, mode)

    def _on_save(self):
        self.settings["server_url"] = self.server_var.get()
        self.settings["hotkey"] = HOTKEY_OPTIONS.get(self.hotkey_var.get(), "scroll_lock")
        self.settings["mode"] = self.mode_var.get()
        self.engine.server_url = self.settings["server_url"]
        self._save_settings()
        self._start_listener()
        self._update_desc()
        self._update_status_ui("idle")

    # ── Keyboard Listener ────────────────────────────────

    def _start_listener(self):
        if self.listener:
            self.listener.stop()

        hotkey_name = self.settings["hotkey"]
        mode = self.settings["mode"]

        def on_press(key):
            if self._match(key, hotkey_name):
                if mode == "ptt":
                    self.engine.start_ptt_recording()
                else:
                    self.engine.toggle_continuous()

        def on_release(key):
            if mode == "ptt" and self._match(key, hotkey_name):
                self.engine.stop_ptt_and_recognize()

        self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.listener.start()

    @staticmethod
    def _match(key, hotkey_name):
        target = KEY_MAP.get(hotkey_name)
        return key == target if target else False

    # ── System Tray ──────────────────────────────────────

    @staticmethod
    def _create_icon():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([22, 6, 42, 34], fill="#4A90D9")
        d.arc([14, 18, 50, 48], start=0, end=180, fill="#4A90D9", width=3)
        d.line([32, 48, 32, 58], fill="#4A90D9", width=3)
        d.line([24, 58, 40, 58], fill="#4A90D9", width=3)
        return img

    def _minimize_to_tray(self):
        self.root.withdraw()
        self.floating.hide()
        if not self.tray:
            menu = pystray.Menu(
                pystray.MenuItem("显示设置", self._show_window),
                pystray.MenuItem("显示浮窗", lambda: self.floating.show()),
                pystray.MenuItem("退出", self._quit),
            )
            self.tray = pystray.Icon("voice_input", self._create_icon(), "语音输入法", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.floating.show()

    def _on_close(self):
        self.root.withdraw()
        self.floating.hide()

    def _quit(self):
        self.engine.stop_continuous()
        if self.listener:
            self.listener.stop()
        if self.tray:
            self.tray.stop()
        self.floating.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = VoiceInputApp()
    app.run()
