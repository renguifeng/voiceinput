import asyncio
import json
import threading

import numpy as np
import sounddevice as sd
import websockets
from pynput import keyboard

FUNASR_URL = "ws://localhost:10096"
SAMPLE_RATE = 16000
SEND_INTERVAL = 0.16
HOTKEY = keyboard.Key.f8


class VoiceInput:
    def __init__(self):
        self.recording = False
        self.audio_buffer = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._kb = keyboard.Controller()

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            with self.lock:
                self.audio_buffer.append(indata[:, 0].copy())

    def _backspace(self, count):
        for _ in range(count):
            self._kb.tap(keyboard.Key.backspace)

    def _type_text(self, text):
        for char in text:
            self._kb.type(char)

    async def _sender(self, ws):
        while not self._stop_event.is_set():
            with self.lock:
                chunks = list(self.audio_buffer)
                self.audio_buffer.clear()
            if chunks:
                await ws.send(np.concatenate(chunks).tobytes())
            await asyncio.sleep(SEND_INTERVAL)
        await ws.send(json.dumps({"is_speaking": False}))

    async def _receiver(self, ws):
        # online_typed: chars typed from online partial results since last offline
        # When offline result comes, backspace online partials, type the correct text
        online_typed = 0
        try:
            async for msg in ws:
                data = json.loads(msg)
                text = data.get("text", "")
                mode = data.get("mode", "")
                if not text:
                    continue

                if mode in ("2pass-offline", "offline"):
                    # Correct result: erase online partials, type accurate text
                    self._backspace(online_typed)
                    self._type_text(text)
                    online_typed = 0
                else:
                    # Online partial: incremental text, just type it
                    self._type_text(text)
                    online_typed += len(text)
        except websockets.ConnectionClosed:
            pass

    async def _connect_and_run(self):
        try:
            async with websockets.connect(FUNASR_URL) as ws:
                await ws.send(json.dumps({
                    "mode": "2pass",
                    "chunk_size": [5, 10, 5],
                    "wav_name": "microphone",
                    "is_speaking": True,
                    "audio_fs": SAMPLE_RATE,
                }))
                await asyncio.gather(self._sender(ws), self._receiver(ws))
        except Exception as e:
            print(f"WebSocket error: {e}")

    def start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.audio_buffer.clear()
        self._stop_event.clear()
        print("Recording... (F8 to stop)")

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=int(SAMPLE_RATE * SEND_INTERVAL),
            callback=self._audio_callback,
        )
        self.stream.start()
        self._ws_thread = threading.Thread(target=self._run_ws_loop, daemon=True)
        self._ws_thread.start()

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self._stop_event.set()
        print("Stopped.")
        if hasattr(self, "stream") and self.stream:
            self.stream.stop()
            self.stream.close()

    def _run_ws_loop(self):
        asyncio.run(self._connect_and_run())

    def toggle(self):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def run(self):
        print("Voice Input Tool")
        print(f"Server: {FUNASR_URL}")
        print("F8 = toggle recording | ESC = quit\n")

        def on_press(key):
            if key == HOTKEY:
                self.toggle()
            elif key == keyboard.Key.esc:
                self.stop_recording()
                return False

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()


if __name__ == "__main__":
    app = VoiceInput()
    app.run()
