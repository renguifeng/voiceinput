"""Cross-platform utilities: clipboard, caret detection."""
import sys

IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = sys.platform.startswith('linux')
IS_MACOS = sys.platform == 'darwin'


# ── Clipboard ────────────────────────────────────────────

def set_clipboard(text: str) -> None:
    """Set system clipboard to text."""
    import pyperclip
    pyperclip.copy(text)


def get_clipboard() -> str:
    """Get current clipboard text."""
    import pyperclip
    try:
        return pyperclip.paste()
    except Exception:
        return ""


# ── Caret detection (Windows only) ───────────────────────

if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes as wintypes

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

    _ACC_LOCATION_IDX = 4

    def _get_caret_via_msaa(hwnd):
        OBJID_CARET = 0xFFFFFFF8
        pacc = ctypes.c_void_p()
        iid_bytes = bytes.fromhex("E0368761" + "3D3D" + "CF11" + "810C" + "00AA00389B71")
        iid = (ctypes.c_byte * 16)(*[b - 256 if b > 127 else b for b in iid_bytes])
        hr = _oleacc.AccessibleObjectFromWindow(hwnd, OBJID_CARET, iid, ctypes.byref(pacc))
        if hr != 0 or not pacc:
            return None
        try:
            vtable = ctypes.c_void_p.from_address(pacc.value).value
            acc_location_func = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_long),
                ctypes.POINTER(ctypes.c_long),
                ctypes.POINTER(ctypes.c_long),
                ctypes.POINTER(ctypes.c_long),
                ctypes.c_void_p,
            )(ctypes.c_void_p.from_address(vtable + _ACC_LOCATION_IDX * ctypes.sizeof(ctypes.c_void_p)).value)

            x, y, w, h = ctypes.c_long(), ctypes.c_long(), ctypes.c_long(), ctypes.c_long()
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
            try:
                vtable = ctypes.c_void_p.from_address(pacc.value).value
                release_func = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
                    ctypes.c_void_p.from_address(vtable + 2 * ctypes.sizeof(ctypes.c_void_p)).value
                )
                release_func(pacc)
            except Exception:
                pass

    def get_caret_screen_pos():
        """Get screen position of the text caret in the foreground app."""
        gui = _GUITHREADINFO()
        gui.cbSize = ctypes.sizeof(_GUITHREADINFO)
        hwnd = _user32.GetForegroundWindow()
        tid = _user32.GetWindowThreadProcessId(hwnd, None)

        if _user32.GetGUIThreadInfo(tid, ctypes.byref(gui)) and gui.hwndCaret:
            pt = _POINT(gui.rcCaret.left, gui.rcCaret.bottom)
            if _user32.ClientToScreen(gui.hwndCaret, ctypes.byref(pt)):
                return pt.x, pt.y

        focus_hwnd = gui.hwndFocus if gui.hwndFocus else hwnd
        pos = _get_caret_via_msaa(focus_hwnd)
        if pos:
            return pos

        return None

else:
    def get_caret_screen_pos():
        """Not supported on this platform; returns None."""
        return None
