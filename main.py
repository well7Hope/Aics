import os
import time
import threading
import requests

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BALE_TOKEN = os.environ.get("BALE_TOKEN")

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MAX_HISTORY = 20

histories = {}
lock = threading.Lock()


def ask_gemini(key, text):
    msg = {"role": "user", "parts": [{"text": text}]}
    with lock:
        h = histories.setdefault(key, [])
        h.append(msg)
        while len(h) > MAX_HISTORY:
            h.pop(0)
        while h and h[0]["role"] != "user":
            h.pop(0)
        contents = list(h)
    try:
        r = requests.post(
            GEMINI_URL,
            json={"contents": contents},
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            timeout=60,
        )
        r.raise_for_status()
        reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        with lock:
            h.append({"role": "model", "parts": [{"text": reply}]})
        return reply
    except Exception as e:
        print("Gemini error:", e)
        with lock:
            if msg in h:
                h.remove(msg)
        return "خطایی رخ داد، لطفاً دوباره تلاش کنید."


class Bot:
    def __init__(self, name, base_url):
        self.name = name
        self.base = base_url
        self.offset = 0

    def call(self, method, timeout=40, **params):
        r = requests.post(f"{self.base}/{method}", json=params, timeout=timeout)
        return r.json()

    def send(self, chat_id, text):
        for i in range(0, len(text), 4000):
            try:
                self.call("sendMessage", chat_id=chat_id, text=text[i:i + 4000])
            except Exception as e:
                print(f"[{self.name}] send error:", e)

    def handle(self, update):
        msg = update.get("message")
        if not msg or "text" not in msg:
            return
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        if text.startswith("/start"):
            self.send(chat_id, "سلام! هر سوالی دارید بپرسید.\nبرای پاک کردن حافظه: /reset")
            return
        if text.startswith("/reset"):
            with lock:
                histories.pop(f"{self.name}:{chat_id}", None)
            self.send(chat_id, "حافظه پاک شد.")
            return
        reply = ask_gemini(f"{self.name}:{chat_id}", text)
        self.send(chat_id, reply)

    def run(self):
        print(f"[{self.name}] started")
        while True:
            start = time.time()
            try:
                data = self.call("getUpdates", offset=self.offset, timeout=30)
                if not data.get("ok"):
                    print(f"[{self.name}] API error:", data)
                    time.sleep(10)
                    continue
                for u in data.get("result", []):
                    self.offset = u["update_id"] + 1
                    threading.Thread(target=self.handle, args=(u,), daemon=True).start()
            except Exception as e:
                print(f"[{self.name}] error:", e)
                time.sleep(5)
            if time.time() - start < 1:
                time.sleep(1)


def main():
    bots = []
    if TELEGRAM_TOKEN:
        bots.append(Bot("telegram", f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"))
    if BALE_TOKEN:
        bots.append(Bot("bale", f"https://tapi.bale.ai/bot{BALE_TOKEN}"))
    if not bots:
        raise SystemExit("حداقل یکی از TELEGRAM_TOKEN یا BALE_TOKEN را تنظیم کنید.")

    threads = [threading.Thread(target=b.run, daemon=True) for b in bots]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
