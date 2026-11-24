"""Telegram notifications (free Bot API). Sending runs on a worker thread so the camera never stalls."""
import queue
import threading

import requests

API = "https://api.telegram.org/bot{token}/{method}"


class Telegram:
    def __init__(self, token="", chat_id="", enabled=True):
        self.token, self.chat_id = token, str(chat_id)
        self.enabled = bool(enabled and token and chat_id)
        self.q = queue.Queue(maxsize=20)
        if self.enabled:
            threading.Thread(target=self._loop, daemon=True).start()
            print("[telegram] notifications ON", flush=True)
        else:
            print("[telegram] notifications OFF (no token/chat_id - see README)", flush=True)

    def send(self, text, jpeg=None):
        if not self.enabled:
            return
        try:
            self.q.put_nowait((text, jpeg))
        except queue.Full:
            pass

    def _loop(self):
        while True:
            text, jpeg = self.q.get()
            try:
                if jpeg is not None:
                    r = requests.post(API.format(token=self.token, method="sendPhoto"),
                                      data={"chat_id": self.chat_id, "caption": text},
                                      files={"photo": ("snap.jpg", jpeg, "image/jpeg")}, timeout=20)
                else:
                    r = requests.post(API.format(token=self.token, method="sendMessage"),
                                      data={"chat_id": self.chat_id, "text": text}, timeout=20)
                if not r.ok:
                    print(f"[telegram] HTTP {r.status_code}: {r.text[:200]}", flush=True)
            except requests.RequestException as e:
                # never print the URL: it contains the bot token
                print(f"[telegram] send failed: {type(e).__name__}", flush=True)
