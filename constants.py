import os
import sys

from pynput import keyboard

# Resolve app directory: next to exe when frozen, script dir otherwise
if getattr(sys, "frozen", False):
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
