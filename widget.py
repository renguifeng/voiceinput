import time

import tkinter as tk

from platform_utils import get_caret_screen_pos as _get_caret_screen_pos


class FloatingWidget:
    """Floating recording card with mic button, timer and pulse animation."""

    TRANSPARENT = "#010101"
    CARD_BG = "#FFFFFF"
    CARD_W = 210
    CARD_H = 76
    CARD_R = 14

    STATE_COLORS = {
        "idle":        "#67C23A",
        "recording":   "#F56C6C",
        "recognizing": "#E6A23C",
        "error":       "#F56C6C",
    }
    STATUS_TEXT = {
        "idle": "就绪",
        "recording": "录音中...",
        "recognizing": "识别中...",
    }

    def __init__(self, parent, on_double_click=None):
        self.on_double_click = on_double_click
        self._drag_x = 0
        self._drag_y = 0
        self._state = "idle"
        self._mode = "continuous"
        self._anim_id = None
        self._pulse_phase = 0.0
        self._rec_start = None
        self._error_text = ""

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)
        self.win.configure(bg=self.TRANSPARENT)
        self.win.wm_attributes("-transparentcolor", self.TRANSPARENT)

        self.canvas = tk.Canvas(self.win, width=self.CARD_W, height=self.CARD_H,
                                bg=self.TRANSPARENT, highlightthickness=0)
        self.canvas.pack()

        self._draw()

        for w in (self.canvas, self.win):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<Double-Button-1>", lambda e: self.on_double_click and self.on_double_click())

        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"+{sw - self.CARD_W - 30}+{sh - self.CARD_H - 80}")

    @staticmethod
    def _round_rect_pts(x1, y1, x2, y2, r):
        return [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        ]

    @staticmethod
    def _blend(fg, bg, t):
        r1, g1, b1 = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
        r2, g2, b2 = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

    def _timer_str(self):
        if self._rec_start is None:
            return "00:00"
        e = int(time.time() - self._rec_start)
        return f"{e//60:02d}:{e%60:02d}"

    def _draw(self):
        c = self.canvas
        c.delete("all")
        W, H = self.CARD_W, self.CARD_H
        color = self.STATE_COLORS[self._state]

        # Shadow
        c.create_polygon(self._round_rect_pts(2, 3, W+1, H+2, self.CARD_R),
                         smooth=True, fill="#E8E8E8", outline="")
        # Card body
        c.create_polygon(self._round_rect_pts(0, 0, W-1, H-1, self.CARD_R),
                         smooth=True, fill=self.CARD_BG, outline="#EBEBEB", width=1)

        mx, my, mr = 42, H // 2, 22

        # Pulse rings
        if self._state == "recording":
            for i in range(3):
                p = (self._pulse_phase + i / 3) % 1.0
                r = mr + p * 12
                c.create_oval(mx-r, my-r, mx+r, my+r,
                              fill="", outline=self._blend(color, self.CARD_BG, p), width=2)

        fill = color if self._state == "recording" else "#F5F7FA"
        icon = "#FFFFFF" if self._state == "recording" else color

        c.create_oval(mx-mr, my-mr, mx+mr, my+mr, fill=fill, outline=color, width=2)

        # Mic icon
        c.create_oval(mx-5, my-9, mx+5, my+1, fill=icon, outline="")
        c.create_arc(mx-9, my-4, mx+9, my+9, start=0, extent=-180,
                     style=tk.ARC, outline=icon, width=2)
        c.create_line(mx, my+4, mx, my+9, fill=icon, width=2)
        c.create_line(mx-4, my+9, mx+4, my+9, fill=icon, width=2)

        # Timer
        c.create_text(mx+mr+14, H//2-10, text=self._timer_str(),
                      font=("Consolas", 20, "bold"), fill="#303133", anchor=tk.W)

        # Status
        if self._state == "error":
            st, sc = self._error_text or "错误", color
        else:
            st = self.STATUS_TEXT.get(self._state, "就绪")
            sc = color if self._state != "idle" else "#909399"
        c.create_text(mx+mr+14, H//2+14, text=st,
                      font=("Microsoft YaHei", 10), fill=sc, anchor=tk.W)

    def update(self, status, mode):
        self._mode = mode
        if status == "recording":
            self._state = "recording"
            self._rec_start = time.time()
            self._start_anim()
        elif status == "识别中...":
            self._state = "recognizing"
            self._rec_start = None
            self._stop_anim()
            self._draw()
        elif status == "idle":
            self._state = "idle"
            self._rec_start = None
            self._error_text = ""
            self._stop_anim()
            self._draw()
        else:
            self._state = "error"
            self._error_text = status
            self._rec_start = None
            self._stop_anim()
            self._draw()

    def _start_anim(self):
        self._stop_anim()
        self._animate()

    def _stop_anim(self):
        if self._anim_id:
            self.win.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate(self):
        if self._state != "recording":
            return
        self._pulse_phase = (self._pulse_phase + 0.04) % 1.0
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
        self._stop_anim()
        self.win.destroy()


class SubtitleBar:
    """Movie-style subtitle bar for intermediate recognition text.

    Sits at the bottom-center of the screen with a semi-transparent
    dark strip and large white text.
    """

    BG = "#000000"
    TRANSPARENT = "#010101"

    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.78)
        self.win.configure(bg=self.TRANSPARENT)
        self.win.wm_attributes("-transparentcolor", self.TRANSPARENT)
        self.win.withdraw()

        self._label = tk.Label(
            self.win, text="", font=("Microsoft YaHei", 22),
            fg="#FFFFFF", bg=self.BG, wraplength=900,
            justify=tk.CENTER, padx=24, pady=10,
        )
        self._label.pack()

    def show(self, text):
        if not text:
            self.win.withdraw()
            return
        self._label.config(text=text)
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = sh - h - 60
        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()

    def hide(self):
        self.win.withdraw()

    def destroy(self):
        self.win.destroy()


class PreviewBubble:
    """Sogou-style candidate preview that follows the text caret.

    Visual style: white rounded card with soft shadow, small arrow
    pointing up to the caret. Clean, minimal, like Sogou default skin.
    """

    TRANSPARENT = "#F0F0F0"  # must differ from BG for transparentcolor

    BG         = "#FFFFFF"
    BORDER     = "#D4D4D4"
    SHADOW     = "#DCDCDC"
    TEXT_COLOR  = "#333333"

    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.96)
        self.win.configure(bg=self.TRANSPARENT)
        self.win.wm_attributes("-transparentcolor", self.TRANSPARENT)
        self.win.withdraw()

        self._canvas = tk.Canvas(self.win, bg=self.TRANSPARENT, highlightthickness=0)
        self._canvas.pack()

        self._font = ("Microsoft YaHei", 12)
        self._pad = (14, 8)
        self._max_w = 300
        self._ptr_w = 10
        self._ptr_h = 6
        self._radius = 6

        self._anchor_x = None
        self._anchor_y = None

    def _update_anchor(self):
        if self._anchor_x is not None:
            return
        pos = _get_caret_screen_pos()
        if pos:
            self._anchor_x, self._anchor_y = pos
        else:
            self._anchor_x = self.win.winfo_pointerx()
            self._anchor_y = self.win.winfo_pointery()

    @staticmethod
    def _round_rect_pts(x1, y1, x2, y2, r):
        """Return polygon points for a rounded rectangle (24 points, smooth)."""
        return [
            x1 + r, y1,
            x1 + r, y1,
            x2 - r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1 + r,
            x1, y1,
        ]

    def show(self, text):
        if not text:
            self.win.withdraw()
            self._anchor_x = None
            self._anchor_y = None
            return

        self._update_anchor()
        c = self._canvas
        c.delete("all")

        # Measure text
        tid = c.create_text(0, 0, text=text, font=self._font, anchor=tk.NW, width=self._max_w)
        bb = c.bbox(tid)
        c.delete(tid)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]

        px, py = self._pad
        pw, ph = self._ptr_w, self._ptr_h
        r = self._radius
        S = 6  # shadow margin

        bw = tw + px * 2
        bh = th + py * 2
        ox, oy = S, ph + S  # body offset
        cw = bw + S * 2
        ch = ph + bh + S * 2
        c.config(width=cw, height=ch)

        # ── Shadow (soft, offset down-right) ──
        c.create_polygon(self._round_rect_pts(ox + 3, oy + 3, ox + bw + 3, oy + bh + 3, r),
                         smooth=True, fill=self.SHADOW, outline="")

        # ── Pointer triangle (white, behind body top edge) ──
        ptr_cx = ox + 16
        c.create_polygon(
            ptr_cx - pw // 2, oy + 2,
            ptr_cx + pw // 2, oy + 2,
            ptr_cx, S - 1,
            fill=self.BG, outline="",
        )

        # ── Body ──
        c.create_polygon(self._round_rect_pts(ox, oy, ox + bw, oy + bh, r),
                         smooth=True, fill=self.BG, outline=self.BORDER, width=1)

        # ── Pointer border lines (slanted sides only) ──
        c.create_line(ptr_cx - pw // 2 + 1, oy + 1, ptr_cx, S - 1, fill=self.BORDER)
        c.create_line(ptr_cx, S - 1, ptr_cx + pw // 2 - 1, oy + 1, fill=self.BORDER)
        # Seal: cover body top border behind pointer
        c.create_rectangle(ptr_cx - pw // 2 + 1, oy - 1, ptr_cx + pw // 2 - 1, oy + 2,
                           fill=self.BG, outline="")

        # ── Text ──
        c.create_text(ox + px, oy + py, text=text, font=self._font,
                      fill=self.TEXT_COLOR, anchor=tk.NW, width=self._max_w)

        # ── Position below anchor ──
        x = self._anchor_x - 8
        y = self._anchor_y + 4
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        if x + cw > sw - 6:
            x = self._anchor_x - cw + 8
        if x < 4:
            x = 4
        if y + ch > sh - 6:
            y = self._anchor_y - ch - 4

        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()

    def hide(self):
        self.win.withdraw()
        self._anchor_x = None
        self._anchor_y = None

    def destroy(self):
        self.win.destroy()
