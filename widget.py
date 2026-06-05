import ctypes
import ctypes.wintypes as wintypes
import math
import struct

import tkinter as tk

# ── Win32 caret detection ────────────────────────────────
_user32 = ctypes.windll.user32
_oleacc = ctypes.windll.oleacc


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong),
                ("flags", ctypes.c_ulong),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", _RECT)]


# IAccessible::accLocation returns (x, y, w, h) via [out] params
# We use the COM vtable to call it directly.
# IAccessible vtable offsets (after IUnknown 3 methods):
#   4 = accLocation, 5 = accHitTest, ...
_ACC_LOCATION_IDX = 4  # 0-based after IUnknown


def _get_caret_via_msaa(hwnd):
    """Try getting caret position via MSAA accessibility (OBJID_CARET)."""
    OBJID_CARET = 0xFFFFFFF8  # -8 as unsigned
    IID_IAccessible = ctypes.c_byte * 16  # GUID as 16 bytes

    pacc = ctypes.c_void_p()
    # {618736E0-3C3D-11CF-810C-00AA00389B71}
    iid_bytes = bytes.fromhex("E0368761" + "3D3C" + "CF11" + "810C" + "00AA00389B71")
    iid = (ctypes.c_byte * 16)(*[b - 256 if b > 127 else b for b in iid_bytes])

    hr = _oleacc.AccessibleObjectFromWindow(hwnd, OBJID_CARET, iid, ctypes.byref(pacc))
    if hr != 0 or not pacc:
        return None

    try:
        # Call IAccessible::accLocation via COM vtable
        # vtable ptr = *(pacc.value)
        vtable = ctypes.c_void_p.from_address(pacc.value).value
        # accLocation is the 4th method (index 4 in vtable, 0-based after IUnknown)
        acc_location_func = ctypes.WINFUNCTYPE(
            ctypes.c_long,       # HRESULT
            ctypes.c_void_p,     # this
            ctypes.POINTER(ctypes.c_long),  # pxLeft
            ctypes.POINTER(ctypes.c_long),  # pyTop
            ctypes.POINTER(ctypes.c_long),  # pcxWidth
            ctypes.POINTER(ctypes.c_long),  # pcyHeight
            ctypes.c_void_p,     # varChild (VARIANT = 0 for self)
        )(ctypes.c_void_p.from_address(vtable + _ACC_LOCATION_IDX * ctypes.sizeof(ctypes.c_void_p)).value)

        x, y, w, h = ctypes.c_long(), ctypes.c_long(), ctypes.c_long(), ctypes.c_long()
        # varChild = VT_I4(3) with value CHILDID_SELF(0) → 3,0,0,0,0,0,0,0 ... 16 bytes
        var_child = (ctypes.c_long * 4)(3, 0, 0, 0)

        hr = acc_location_func(pacc, ctypes.byref(x), ctypes.byref(y),
                               ctypes.byref(w), ctypes.byref(h), var_child)
        if hr != 0:
            return None
        if x.value == 0 and y.value == 0:
            return None
        return x.value, y.value + h.value
    except Exception:
        return None
    finally:
        # Release COM object (IUnknown::Release = vtable[2])
        try:
            vtable = ctypes.c_void_p.from_address(pacc.value).value
            release_func = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
                ctypes.c_void_p.from_address(vtable + 2 * ctypes.sizeof(ctypes.c_void_p)).value
            )
            release_func(pacc)
        except Exception:
            pass


def _get_caret_screen_pos():
    """Get screen position of the text caret in the foreground app.

    Strategy:
    1. GetGUIThreadInfo — works for standard Win32 apps (Notepad, Word…)
    2. MSAA OBJID_CARET — works for many more apps (Chrome, Electron…)
    3. Fallback to None (caller uses mouse position)
    """
    gui = _GUITHREADINFO()
    gui.cbSize = ctypes.sizeof(_GUITHREADINFO)

    hwnd = _user32.GetForegroundWindow()
    tid = _user32.GetWindowThreadProcessId(hwnd, None)

    # Method 1: standard caret API
    if _user32.GetGUIThreadInfo(tid, ctypes.byref(gui)) and gui.hwndCaret:
        pt = _POINT(gui.rcCaret.left, gui.rcCaret.bottom)
        if _user32.ClientToScreen(gui.hwndCaret, ctypes.byref(pt)):
            return pt.x, pt.y

    # Method 2: MSAA accessibility
    focus_hwnd = gui.hwndFocus if gui.hwndFocus else hwnd
    pos = _get_caret_via_msaa(focus_hwnd)
    if pos:
        return pos

    return None


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

        W = 80
        H = 80
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
