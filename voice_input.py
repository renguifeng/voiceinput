import asyncio
import json
import math
import os
import threading

import numpy as np
import sounddevice as sd
import websockets
from pynput import keyboard

import tkinter as tk
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw

import sys

# Resolve app directory: next to exe when frozen, script dir otherwise
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
SAMPLE_RATE = 16000
SEND_INTERVAL = 0.16

HOTKEY_OPTIONS = {
    "Scroll Lock": "scroll_lock",
    "F8": "f8",
    "F9": "f9",
    "F10": "f10",
    "Pause/Break": "pause",
    "Insert": "insert",
    "Ctrl (左)": "ctrl_l",
    "Ctrl (右)": "ctrl_r",
}

KEY_MAP = {
    "scroll_lock": keyboard.Key.scroll_lock,
    "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9,
    "f10": keyboard.Key.f10,
    "pause": keyboard.Key.pause,
    "insert": keyboard.Key.insert,
    "ctrl_l": keyboard.Key.ctrl_l,
    "ctrl_r": keyboard.Key.ctrl_r,
}


class VoiceInputEngine:
    def __init__(self, on_status_change=None):
        self.recording = False
        self.audio_buffer = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._kb = keyboard.Controller()
        self.server_url = "ws://localhost:10096"
        self.stream = None
        self.on_status_change = on_status_change or (lambda s: None)
        self._clipboard = None  # lazy init

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            with self.lock:
                self.audio_buffer.append(indata[:, 0].copy())

    def _get_clipboard(self):
        """Lazy init tkinter clipboard helper (runs in main thread via after)."""
        if self._clipboard is None:
            import tkinter as tk
            self._clipboard = tk.Tk()
            self._clipboard.withdraw()
        return self._clipboard

    def _backspace(self, count):
        for _ in range(count):
            self._kb.tap(keyboard.Key.backspace)

    def _paste_text(self, text):
        """Type text via clipboard paste — fast and reliable for Chinese."""
        if not text:
            return
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        # Ctrl+V
        self._kb.press(keyboard.Key.ctrl)
        self._kb.press("v")
        self._kb.release("v")
        self._kb.release(keyboard.Key.ctrl)
        root.destroy()

    # ── Continuous mode: real-time streaming ──────────────

    async def _stream_sender(self, ws):
        while not self._stop_event.is_set():
            with self.lock:
                chunks = list(self.audio_buffer)
                self.audio_buffer.clear()
            if chunks:
                await ws.send(np.concatenate(chunks).tobytes())
            await asyncio.sleep(SEND_INTERVAL)
        await ws.send(json.dumps({"is_speaking": False}))

    async def _stream_receiver(self, ws):
        online_buf = ""
        try:
            async for msg in ws:
                data = json.loads(msg)
                text = data.get("text", "")
                mode = data.get("mode", "")
                if not text:
                    continue
                if mode in ("2pass-offline", "offline"):
                    # Backspace all online text typed for this segment
                    self._backspace(len(online_buf))
                    # Paste the accurate offline result
                    self._paste_text(text)
                    online_buf = ""
                else:
                    # Online delta: paste incremental text
                    self._paste_text(text)
                    online_buf += text
        except websockets.ConnectionClosed:
            pass

    async def _continuous_run(self):
        try:
            async with websockets.connect(self.server_url) as ws:
                await ws.send(json.dumps({
                    "mode": "2pass",
                    "chunk_size": [5, 10, 5],
                    "wav_name": "microphone",
                    "is_speaking": True,
                    "audio_fs": SAMPLE_RATE,
                }))
                await asyncio.gather(self._stream_sender(ws), self._stream_receiver(ws))
        except Exception as e:
            self.on_status_change(f"连接错误: {e}")

    def start_continuous(self):
        if self.recording:
            return
        self.recording = True
        self.audio_buffer.clear()
        self._stop_event.clear()
        self.on_status_change("recording")

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=int(SAMPLE_RATE * SEND_INTERVAL),
            callback=self._audio_callback,
        )
        self.stream.start()
        threading.Thread(target=lambda: asyncio.run(self._continuous_run()), daemon=True).start()

    def stop_continuous(self):
        if not self.recording:
            return
        self.recording = False
        self._stop_event.set()
        self.on_status_change("idle")
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def toggle_continuous(self):
        if self.recording:
            self.stop_continuous()
        else:
            self.start_continuous()

    # ── PTT mode: press to start real-time, release to stop ──

    def start_ptt_recording(self):
        # reuse continuous mode engine
        self.start_continuous()

    def stop_ptt_and_recognize(self):
        # reuse continuous mode engine
        self.stop_continuous()


class FloatingWidget:
    """Sci-fi style semi-transparent floating status widget."""

    BG = "#0D1117"
    TRANSPARENT = "#010101"  # color used for transparent corners

    RING_COLORS = {
        "idle":       ("#00E5A0", "#004D36"),
        "recording":  ("#FF3B5C", "#4D0015"),
        "recognizing":("#FFB800", "#4D3800"),
        "error":      ("#FF3B5C", "#4D0015"),
    }

    def __init__(self, parent, on_double_click=None):
        self.on_double_click = on_double_click
        self._drag_x = 0
        self._drag_y = 0
        self._state = "idle"
        self._mode = "continuous"
        self._anim_id = None
        self._pulse_phase = 0
        self._glow_phase = 0.0

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.88)
        self.win.configure(bg=self.TRANSPARENT)
        self.win.wm_attributes("-transparentcolor", self.TRANSPARENT)

        W, H = 80, 80
        self._size = W
        self.canvas = tk.Canvas(self.win, width=W, height=H,
                                bg=self.TRANSPARENT, highlightthickness=0)
        self.canvas.pack(padx=0, pady=0)

        self._draw()
        self._start_anim()

        # drag
        for w in (self.canvas, self.win):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<Double-Button-1>", lambda e: self.on_double_click and self.on_double_click())

        # position bottom-right
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"+{sw - W - 30}+{sh - H - 80}")

    def _accent(self):
        return self.RING_COLORS[self._state][0]

    def _dim(self):
        return self.RING_COLORS[self._state][1]

    @staticmethod
    def _lerp_color(c1, c2, t):
        """Linear interpolate between two hex colors. t=0 -> c1, t=1 -> c2."""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw(self):
        c = self.canvas
        c.delete("all")
        W = self._size
        cx = W // 2
        cy = W // 2
        color = self._accent()
        dim = self._dim()

        # --- dark circular background ---
        c.create_oval(cx - 40, cy - 40, cx + 40, cy + 40,
                      fill=self.BG, outline="")

        # --- expanding glow rings (always active, speed varies by state) ---
        num_rings = 5
        for i in range(num_rings):
            phase = (self._glow_phase + i / num_rings) % 1.0
            r = 26 + phase * 14
            fade = 1.0 - phase
            brightness = fade * 0.8
            if self._state == "idle":
                brightness *= 0.5
            ring_color = self._lerp_color(self.BG, color, brightness)
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill="", outline=ring_color, width=1.5)

        # --- outer static glow rings ---
        for r, w in [(38, 1), (35, 1), (32, 1)]:
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill="", outline=dim, width=w)

        # --- rotating tick marks ---
        for deg in range(0, 360, 30):
            rad = math.radians(deg + self._pulse_phase)
            r = 35
            x = cx + r * math.cos(rad)
            y = cy + r * math.sin(rad)
            dot_r = 1.5 if deg % 60 == 0 else 1
            c.create_oval(x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                          fill=dim, outline="")

        # --- main ring (fixed width) ---
        c.create_oval(cx - 26, cy - 26, cx + 26, cy + 26,
                      fill="", outline=color, width=2)

        # --- inner glow ring ---
        c.create_oval(cx - 22, cy - 22, cx + 22, cy + 22,
                      fill="", outline=dim, width=1)

        # --- mode text in center ---
        mode_label = "HOLD" if self._mode == "ptt" else "LIVE"
        c.create_text(cx, cy, text=mode_label, fill=color,
                      font=("Consolas", 12, "bold"))

        # --- status dot at top ---
        c.create_oval(cx - 3, cy - 34, cx + 3, cy - 28,
                      fill=color, outline="")

    def update(self, status, mode):
        self._mode = mode
        if status == "recording":
            self._state = "recording"
        elif status == "识别中...":
            self._state = "recognizing"
        elif status == "idle":
            self._state = "idle"
        else:
            self._state = "error"

        self._draw()
        self._start_anim()

    def _start_anim(self):
        if self._anim_id:
            self.win.after_cancel(self._anim_id)
            self._anim_id = None
        self._animate()

    def _animate(self):
        if self._state == "recording":
            self._pulse_phase = (self._pulse_phase + 6) % 360
            self._glow_phase = (self._glow_phase + 0.06) % 1.0
            self._draw()
            self._anim_id = self.win.after(50, self._animate)
        elif self._state == "recognizing":
            self._pulse_phase = (self._pulse_phase + 3) % 360
            self._glow_phase = (self._glow_phase + 0.025) % 1.0
            self._draw()
            self._anim_id = self.win.after(60, self._animate)
        else:
            # idle: slow breathing, ticks still
            self._glow_phase = (self._glow_phase + 0.012) % 1.0
            self._draw()
            self._anim_id = self.win.after(80, self._animate)

    def _on_drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _on_drag_move(self, e):
        x = self.win.winfo_x() + e.x - self._drag_x
        y = self.win.winfo_y() + e.y - self._drag_y
        self.win.geometry(f"+{x}+{y}")

    def show(self):
        self.win.deiconify()

    def hide(self):
        self.win.withdraw()

    def destroy(self):
        if self._anim_id:
            self.win.after_cancel(self._anim_id)
        self.win.destroy()


class VoiceInputApp:
    def __init__(self):
        self.engine = VoiceInputEngine(on_status_change=self._on_engine_status)
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

    def _match(self, key, hotkey_name):
        target = KEY_MAP.get(hotkey_name)
        return key == target if target else False

    # ── System Tray ──────────────────────────────────────

    def _create_icon(self):
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
