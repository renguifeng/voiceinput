import asyncio
import json
import numpy as np
import sounddevice as sd
import websockets

FUNASR_URL = "ws://localhost:10096"
SAMPLE_RATE = 16000
SEND_INTERVAL = 0.16


async def debug():
    print(f"Connecting to {FUNASR_URL} ...")
    async with websockets.connect(FUNASR_URL) as ws:
        await ws.send(json.dumps({
            "mode": "2pass",
            "chunk_size": [5, 10, 5],
            "wav_name": "microphone",
            "is_speaking": True,
            "audio_fs": SAMPLE_RATE,
        }))
        print("Connected. Recording for 8 seconds... Speak now!\n")

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=int(SAMPLE_RATE * SEND_INTERVAL),
        )
        stream.start()

        import time
        start = time.time()
        msg_count = 0

        while time.time() - start < 8:
            audio, _ = stream.read(int(SAMPLE_RATE * SEND_INTERVAL))
            await ws.send(audio[:, 0].tobytes())
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.3)
                msg_count += 1
                data = json.loads(msg)
                print(f"[#{msg_count}] is_final={data.get('is_final')}, "
                      f"mode={data.get('mode','?')}, "
                      f"text='{data.get('text','')}'")
            except asyncio.TimeoutError:
                pass

        await ws.send(json.dumps({"is_speaking": False}))
        # read remaining results
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                msg_count += 1
                data = json.loads(msg)
                print(f"[#{msg_count}] is_final={data.get('is_final')}, "
                      f"mode={data.get('mode','?')}, "
                      f"text='{data.get('text','')}'")
        except asyncio.TimeoutError:
            pass

        stream.stop()
        stream.close()
        print(f"\nDone. Total messages: {msg_count}")


asyncio.run(debug())
