import asyncio
import ctypes
import json
import threading

import numpy as np
import sounddevice as sd
import websockets
from pynput import keyboard

from constants import SAMPLE_RATE, SEND_INTERVAL

# ── Win32 clipboard API (init once, thread-safe) ──────────
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_kernel32.GlobalAlloc.restype = ctypes.c_void_p
_kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
_user32.OpenClipboard.restype = ctypes.c_int
_user32.OpenClipboard.argtypes = [ctypes.c_void_p]
_user32.SetClipboardData.restype = ctypes.c_void_p
_user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]


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

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            with self.lock:
                self.audio_buffer.append(indata[:, 0].copy())

    @staticmethod
    def _set_clipboard(text):
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        data = text.encode("utf-16-le") + b"\x00\x00"
        h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        p = _kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        _kernel32.GlobalUnlock(h)

        _user32.OpenClipboard(0)
        _user32.EmptyClipboard()
        _user32.SetClipboardData(CF_UNICODETEXT, h)
        _user32.CloseClipboard()

    def _paste_text(self, text):
        if not text:
            return
        self._set_clipboard(text)
        self._kb.press(keyboard.Key.ctrl)
        self._kb.press("v")
        self._kb.release("v")
        self._kb.release(keyboard.Key.ctrl)

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
        try:
            async for msg in ws:
                data = json.loads(msg)
                text = data.get("text", "")
                mode = data.get("mode", "")
                if not text:
                    continue
                if mode in ("2pass-offline", "offline"):
                    self._paste_text(text)
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
        self.start_continuous()

    def stop_ptt_and_recognize(self):
        self.stop_continuous()
