"""Ekran bölgesindeki İngilizce altyazıyı OCR ile okur, Ollama ile Türkçeye çevirir, WebSocket ile yayınlar.

Kullanım:
    python server.py --region 0,800,1920,280
    python server.py --selftest
"""
import argparse
import asyncio
import json
import time
import urllib.request

import mss
import websockets
from websockets.asyncio.server import serve
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

PROMPT = (
    "You are a professional English (en) to Turkish (tr) translator. Your goal is to accurately "
    "convey the meaning and nuances of the original English text while adhering to Turkish grammar, "
    "vocabulary, and cultural sensitivities. Produce only the Turkish translation, without any "
    "additional explanations or commentary. Please translate the following English text into Turkish:"
    "\n\n\n{text}"
)


def make_ocr():
    langs = [l.language_tag for l in OcrEngine.available_recognizer_languages]
    if not any(t.startswith("en") for t in langs):
        print(f"UYARI: İngilizce OCR paketi yok (kurulu: {langs}). Yönetici PowerShell'de:\n"
              "  Add-WindowsCapability -Online -Name 'Language.OCR~~~en-US~0.0.1.0'\n"
              "Şimdilik kurulu dille devam ediliyor, doğruluk düşük olabilir.")
        return OcrEngine.try_create_from_user_profile_languages()
    return OcrEngine.try_create_from_language(Language("en-US"))


async def ocr(engine, shot):
    w = DataWriter()
    w.write_bytes(shot.bgra)
    bmp = SoftwareBitmap.create_copy_from_buffer(w.detach_buffer(), BitmapPixelFormat.BGRA8, shot.width, shot.height)
    result = await engine.recognize_async(bmp)
    return " ".join(line.text for line in result.lines).strip()


def stable(state, text):
    """Metin art arda 2 karede aynı kaldığında ve son gönderilenden farklıysa döndürür.
    Ekrandan kalkınca "" döndürür (altyazıyı temizlemek için). Aksi halde None."""
    # ponytail: birebir eşleşme; OCR kareler arası 1 harf oynatırsa satır gecikir, gerekirse benzerlik oranı (difflib) kullan
    prev, state["prev"] = state["prev"], text
    if text != prev or text == state["sent"]:
        return None
    state["sent"] = text
    return text


def translate(text, model, cache):
    if text not in cache:
        body = json.dumps({"model": model, "prompt": PROMPT.format(text=text), "stream": False,
                           "keep_alive": "30m", "options": {"temperature": 0}}).encode()
        req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            cache[text] = json.load(r)["response"].strip()
    return cache[text]


async def main(a):
    x, y, w, h = map(int, a.region.split(","))
    engine, cache, state, clients = make_ocr(), {}, {"prev": None, "sent": ""}, set()

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with serve(handler, "0.0.0.0", a.port):
        print(f"ws://0.0.0.0:{a.port} dinleniyor, bölge {a.region}, model {a.model}")
        with mss.MSS() as sct:
            while True:
                t0 = time.perf_counter()
                shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                t1 = time.perf_counter()
                text = await ocr(engine, shot)
                t2 = time.perf_counter()
                line = stable(state, text)
                if line is not None:
                    try:
                        tr = await asyncio.to_thread(translate, line, a.model, cache) if line else ""
                    except Exception as e:  # Ollama kapalı/model yok: döngüyü öldürme
                        print("çeviri hatası:", e)
                        tr = ""
                    t3 = time.perf_counter()
                    websockets.broadcast(clients, json.dumps({"en": line, "tr": tr}, ensure_ascii=False))
                    if line:
                        print(f"[yakala {1000*(t1-t0):.0f} ms | ocr {1000*(t2-t1):.0f} ms | çeviri {1000*(t3-t2):.0f} ms] {line} -> {tr}")
                await asyncio.sleep(max(0, a.interval - (time.perf_counter() - t0)))


def selftest():
    s = {"prev": None, "sent": ""}
    assert [stable(s, t) for t in ["", "Hel", "Hello", "Hello", "Hello", "", ""]] == [None, None, None, "Hello", None, None, ""]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="0,780,1920,300", help="x,y,genişlik,yükseklik (piksel)")
    p.add_argument("--model", default="translategemma:12b")
    p.add_argument("--interval", type=float, default=0.15, help="kareler arası saniye")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        selftest()
        print("selftest ok")
    else:
        asyncio.run(main(a))
