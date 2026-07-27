import asyncio
import json
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import websockets
from pynput import keyboard

from constants import SAMPLE_RATE, SEND_INTERVAL
from platform_utils import set_clipboard, get_clipboard


class VoiceInputEngine:
    def __init__(self, on_status_change=None, on_partial_text=None, paste_delay=0.02):
        self.recording = False
        self.audio_buffer = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._kb = keyboard.Controller()
        self.server_url = "ws://localhost:10096"
        self.stream = None
        self.on_status_change = on_status_change or (lambda s: None)
        self.on_partial_text = on_partial_text or (lambda t: None)
        self._paste_delay = paste_delay  # seconds

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            with self.lock:
                self.audio_buffer.append(indata[:, 0].copy())

    def _paste_text(self, text):
        """Paste text via clipboard + hotkey."""
        if not text:
            return
        set_clipboard(text)
        # macOS uses Cmd+V, Windows/Linux use Ctrl+V
        mod_key = keyboard.Key.cmd if sys.platform == 'darwin' else keyboard.Key.ctrl
        self._kb.press(mod_key)
        self._kb.press("v")
        self._kb.release("v")
        self._kb.release(mod_key)
        time.sleep(self._paste_delay)

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
        current_segment = ""
        try:
            async for msg in ws:
                data = json.loads(msg)
                text = data.get("text", "")
                mode = data.get("mode", "")
                if not text:
                    continue
                if mode in ("2pass-offline", "offline"):
                    self._paste_text(text)
                    current_segment = ""
                    self.on_partial_text("")
                else:
                    current_segment += text
                    self.on_partial_text(current_segment)
        except websockets.ConnectionClosed:
            pass

    async def _continuous_run(self):
        # Save clipboard before we start modifying it
        saved = get_clipboard()
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
        finally:
            # Restore clipboard after session ends
            if saved is not None:
                set_clipboard(saved)

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
