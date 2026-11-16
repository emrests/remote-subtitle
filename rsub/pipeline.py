"""Yakala → OCR → sabitle → konuşmacıları ayır → çevir → yayınla döngüsü."""
import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import mss
from PIL import Image

from . import store
from .capture import grab, target_rect, to_pixels
from .ocr import ocr
from .speaker import split_speakers
from .translate import translate

SLOW_MS = 1000
ERROR_PAUSE = 1.0  # beklenmedik hatadan sonra bekleme (sn)


def stable(state: dict, text: str) -> str | None:
    """Metin art arda 2 karede aynı kaldığında ve son gönderilenden farklıysa döndürür.
    Ekrandan kalkınca "" döndürür (altyazıyı temizlemek için). Aksi halde None."""
    # ponytail: birebir eşleşme; OCR kareler arası 1 harf oynatırsa satır gecikir, gerekirse benzerlik oranı (difflib) kullan
    prev, state["prev"] = state["prev"], text
    if text != prev or text == state["sent"]:
        return None
    state["sent"] = text
    return text


def build_lines(text: str, profile: dict, tr: Callable[[str], str]) -> tuple[list[dict], list[str]]:
    """Satırları oluşturur; profili değiştirmez, yeni görülen konuşmacıları döndürür (çağıran ekler)."""
    lines, new = [], []
    for speaker, en in split_speakers(text):
        color = None
        if speaker:
            known = profile["speakers"].get(speaker)
            if known is None and speaker not in new:
                new.append(speaker)
            color = (known or {}).get("color") or profile["style"]["nameColor"]
        try:
            out = tr(en)
        except Exception:  # Ollama kapalı / model yok: satırı düşürme, İngilizcesini göster
            out = en
        lines.append({"speaker": speaker, "color": color, "en": en, "tr": out})
    return lines, new


@dataclass
class Runtime:
    settings: dict
    profile: dict
    emit: Callable[[dict], None]
    engine: Any = None
    cache: dict = field(default_factory=dict)
    timings: deque = field(default_factory=lambda: deque(maxlen=10))
    last_lines: list = field(default_factory=list)
    model_ready: bool = True  # App, Ollama'da model kurulu mu diye günceller
    on_frame: Callable | None = None  # her karede kaynak dikdörtgeniyle (ya da None) çağrılır: katman konumu
    status: dict = field(default_factory=lambda: {"window": False, "last": None, "avgMs": None,
                                                  "slow": False, "error": None, "running": True})


async def run(rt: Runtime, interval: float = 0.15) -> None:
    state = {"prev": None, "sent": ""}

    def tr(en: str) -> str:
        if not rt.model_ready:  # model inerken Ollama'ya istek gönderme (404 döner); İngilizce göster
            rt.status["error"] = "Çeviri modeli hazır değil; hazır olunca çeviri başlar. Şimdilik İngilizce gösteriliyor."
            raise RuntimeError("model hazır değil")
        try:
            out = translate(en, rt.settings["model"], rt.profile["glossary"], rt.cache)
            rt.status["error"] = None
            return out
        except Exception as e:
            rt.status["error"] = f"Çeviri hatası: {e}"
            raise

    with mss.MSS() as sct:
        while True:
            t0 = time.perf_counter()
            try:
                await _frame(rt, sct, state, tr, t0)
            except Exception as e:  # tek bir karedeki hata döngüyü (ve sunucuyu) öldürmesin
                rt.status["error"] = f"Okuma hatası: {e}"
                await asyncio.sleep(ERROR_PAUSE)
                continue
            await asyncio.sleep(max(0, interval - (time.perf_counter() - t0)))


def _clear(rt: Runtime, state: dict) -> None:
    if rt.last_lines:  # eski altyazı TV'de asılı kalmasın
        rt.last_lines = []
        rt.emit({"type": "lines", "lines": []})
    state.update(prev=None, sent="")


async def _frame(rt: Runtime, sct, state: dict, tr, t0: float) -> None:
    rt.status["running"] = rt.settings.get("running", True)
    if not rt.status["running"]:  # kullanıcı durdurdu: okuma yapma, ama pencere durumunu göster
        rt.status["window"] = target_rect(rt.profile["source"]) is not None
        _clear(rt, state)
        if rt.on_frame:
            rt.on_frame(None)
        await asyncio.sleep(0.3)
        return
    profile = rt.profile  # panel her an değiştirebilir; her karede yeniden okunur
    rect = target_rect(profile["source"])
    rt.status["window"] = rect is not None
    if rect is None:  # pencere kapandı/küçüldü
        _clear(rt, state)
        if rt.on_frame:
            rt.on_frame(None)
        await asyncio.sleep(1)
        return
    shot = grab(sct, to_pixels(profile["region"], rect))
    t1 = time.perf_counter()
    region_img = Image.frombytes("RGB", shot.size, shot.rgb) if shot is not None and rt.on_frame else None
    text = await ocr(rt.engine, shot)
    t2 = time.perf_counter()
    line = stable(state, text)
    if line is None:
        if rt.on_frame:
            rt.on_frame(rect, region_img)
        return
    lines, new = await asyncio.to_thread(build_lines, line, profile, tr)
    t3 = time.perf_counter()
    rt.last_lines = lines
    rt.emit({"type": "lines", "lines": lines})
    if rt.on_frame:
        rt.on_frame(rect, region_img)
    # Yeni konuşmacılar döngü iş parçacığında eklenir (panel komutlarıyla yarışmasın);
    # panel bu arada profili değiştirdiyse eski profile yazılmaz.
    if new and rt.profile is profile:
        for name in new:
            profile["speakers"].setdefault(name, {"color": None, "voice": None})
        store.save_profile(profile)
    if line:
        rt.timings.append(round(1000 * (t3 - t0)))
        avg = round(sum(rt.timings) / len(rt.timings))
        rt.status.update(last={"capture": round(1000 * (t1 - t0)), "ocr": round(1000 * (t2 - t1)),
                               "translate": round(1000 * (t3 - t2))},
                         avgMs=avg, slow=avg > SLOW_MS, lastLine={"en": line, "lines": lines})
