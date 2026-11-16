"""Yakala → OCR → sabitle → konuşmacıları ayır → çevir → yayınla döngüsü."""
import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import mss

from . import store
from .capture import grab, target_rect, to_pixels
from .ocr import ocr
from .speaker import split_speakers
from .translate import translate

SLOW_MS = 1000


def stable(state: dict, text: str) -> str | None:
    """Metin art arda 2 karede aynı kaldığında ve son gönderilenden farklıysa döndürür.
    Ekrandan kalkınca "" döndürür (altyazıyı temizlemek için). Aksi halde None."""
    # ponytail: birebir eşleşme; OCR kareler arası 1 harf oynatırsa satır gecikir, gerekirse benzerlik oranı (difflib) kullan
    prev, state["prev"] = state["prev"], text
    if text != prev or text == state["sent"]:
        return None
    state["sent"] = text
    return text


def build_lines(text: str, profile: dict, tr: Callable[[str], str]) -> tuple[list[dict], bool]:
    lines, changed = [], False
    for speaker, en in split_speakers(text):
        color = None
        if speaker:
            if speaker not in profile["speakers"]:
                profile["speakers"][speaker] = {"color": None, "voice": None}
                changed = True
            color = profile["speakers"][speaker]["color"] or profile["style"]["nameColor"]
        try:
            out = tr(en)
        except Exception:  # Ollama kapalı / model yok: satırı düşürme, İngilizcesini göster
            out = en
        lines.append({"speaker": speaker, "color": color, "en": en, "tr": out})
    return lines, changed


@dataclass
class Runtime:
    settings: dict
    profile: dict
    emit: Callable[[dict], None]
    engine: Any = None
    cache: dict = field(default_factory=dict)
    timings: deque = field(default_factory=lambda: deque(maxlen=10))
    last_lines: list = field(default_factory=list)
    status: dict = field(default_factory=lambda: {"window": False, "last": None, "avgMs": None,
                                                  "slow": False, "error": None})


async def run(rt: Runtime, interval: float = 0.15) -> None:
    state = {"prev": None, "sent": ""}

    def tr(en: str) -> str:
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
            profile = rt.profile  # panel her an değiştirebilir; her karede yeniden okunur
            rect = target_rect(profile["source"])
            rt.status["window"] = rect is not None
            if rect is None:
                await asyncio.sleep(1)
                continue
            shot = grab(sct, to_pixels(profile["region"], rect))
            t1 = time.perf_counter()
            text = await ocr(rt.engine, shot)
            t2 = time.perf_counter()
            line = stable(state, text)
            if line is not None:
                lines, changed = await asyncio.to_thread(build_lines, line, profile, tr)
                t3 = time.perf_counter()
                rt.last_lines = lines
                rt.emit({"type": "lines", "lines": lines})
                if changed and rt.profile is profile:  # panel bu arada profili değiştirdiyse eskisini yazma
                    store.save_profile(profile)
                if line:
                    total = round(1000 * (t3 - t0))
                    rt.timings.append(total)
                    avg = round(sum(rt.timings) / len(rt.timings))
                    rt.status.update(last={"capture": round(1000 * (t1 - t0)), "ocr": round(1000 * (t2 - t1)),
                                           "translate": round(1000 * (t3 - t2))},
                                     avgMs=avg, slow=avg > SLOW_MS, lastLine={"en": line, "lines": lines})
            await asyncio.sleep(max(0, interval - (time.perf_counter() - t0)))
