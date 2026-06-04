import math

import tkinter as tk


class FloatingWidget:
    """Sci-fi style semi-transparent floating status widget."""

    BG = "#0D1117"
    TRANSPARENT = "#010101"

    RING_COLORS = {
        "idle":        ("#00E5A0", "#004D36"),
        "recording":   ("#FF3B5C", "#4D0015"),
        "recognizing": ("#FFB800", "#4D3800"),
        "error":       ("#FF3B5C", "#4D0015"),
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

        for w in (self.canvas, self.win):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<Double-Button-1>", lambda e: self.on_double_click and self.on_double_click())

        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"+{sw - W - 30}+{sh - H - 80}")

    def _accent(self):
        return self.RING_COLORS[self._state][0]

    def _dim(self):
        return self.RING_COLORS[self._state][1]

    @staticmethod
    def _lerp_color(c1, c2, t):
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

        c.create_oval(cx - 40, cy - 40, cx + 40, cy + 40,
                      fill=self.BG, outline="")

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

        for r, w in [(38, 1), (35, 1), (32, 1)]:
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill="", outline=dim, width=w)

        for deg in range(0, 360, 30):
            rad = math.radians(deg + self._pulse_phase)
            r = 35
            x = cx + r * math.cos(rad)
            y = cy + r * math.sin(rad)
            dot_r = 1.5 if deg % 60 == 0 else 1
            c.create_oval(x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                          fill=dim, outline="")

        c.create_oval(cx - 26, cy - 26, cx + 26, cy + 26,
                      fill="", outline=color, width=2)

        c.create_oval(cx - 22, cy - 22, cx + 22, cy + 22,
                      fill="", outline=dim, width=1)

        mode_label = "HOLD" if self._mode == "ptt" else "LIVE"
        c.create_text(cx, cy, text=mode_label, fill=color,
                      font=("Consolas", 12, "bold"))

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
