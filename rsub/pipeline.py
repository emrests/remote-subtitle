"""Yakala → OCR → sabitle → konuşmacıları ayır → çevir → yayınla döngüsü."""
import asyncio
import difflib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import mss
from PIL import Image

from . import ps5, store
from .capture import grab, target_rect, to_pixels
from .ocr import read_best as ocr  # normal okuma, zayıfsa parlak-yazı yöntemi
from .speaker import split_speakers
from .cleanup import GARBAGE_BELOW, clean
from .translate import profile_context, translate

SLOW_MS = 1000
ERROR_PAUSE = 1.0  # beklenmedik hatadan sonra bekleme (sn)
EXTRA_INTERVAL = 0.5  # ek bölgeler (sağ üst görev yazısı vb.) bu sıklıkta okunur: gecikme önemsiz
HOLD_MIN, HOLD_MAX = 0.5, 4.0  # altyazı gidince çeviri, gelirken geciktiği kadar (bu sınırlarda) daha kalır (sn)
SUB_WAIT = 5.0  # ek bölge çevirisi, altyazının çevirisi bitsin diye en çok bu kadar bekler


_JITTER = str.maketrans({"I": "l", "|": "l", "1": "l", "’": "'", "‘": "'", "`": "'"})


def _norm(text: str) -> str:
    """OCR'ın kareden kareye oynattığı ayrıntıları siler: I/l/| karışması, uçtaki çöp karakterler, boşluklar."""
    t = " ".join((text or "").translate(_JITTER).split())
    return t.strip(" •·.,;:-_~*'\"").lower()


def _same(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a is b
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return na == nb
    return na == nb or difflib.SequenceMatcher(None, na, nb).ratio() >= 0.9


def _union(a: tuple | None, b: tuple | None) -> tuple | None:
    if a is None or b is None:
        return a or b
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return x0, y0, x1 - x0, y1 - y0


def stable(state: dict, text: str, score: float = 1.0) -> str | None:
    """Metin art arda 2 karede (OCR titremesine rağmen) aynı kaldığında ve son gönderilenden farklıysa döndürür.
    Aynı satırın belirgin biçimde daha eksiksiz okunan hali (sözlük puanı +0,15) gelirse onu da döndürür
    (harf harf beliren yazı: "Get to t cliff edg" → "Get to the cliff edge.").
    Ekrandan kalkınca "" döndürür (altyazıyı temizlemek için). Aksi halde None."""
    prev, state["prev"] = state["prev"], text
    if not _same(text, prev):
        state["run"] = 1
        return None
    state["run"] = state.get("run", 1) + 1
    # yazı belirirken/kaybolurken yarım okunabilir ("I tin ink..", "tinenn"): satır değişmeden 2 kare,
    # sözlükte olmayan kelime varsa 3 kare kalmadan çevirme. Ekran bu sırada boş kapakla kapalı.
    # ponytail: hız için 3/4'ten indirildi (~0,1 sn); yarım satır çevrilirse geri 3/4 yapılır
    if text and state["run"] < (2 if score >= 0.999 else 3):
        return None
    if _same(text, state["sent"]):
        if text and _norm(text) == _norm(prev) and score > state.get("score", 1.0) + 0.15:
            state["sent"], state["score"] = text, score
            return text
        return None
    state["sent"], state["score"] = text, score
    return text


def build_lines(text: str, profile: dict, tr: Callable[[str], str]) -> tuple[list[dict], list[str]]:
    """Satırları oluşturur; profili değiştirmez, yeni görülen konuşmacıları döndürür (çağıran ekler)."""
    lines, new = [], []
    for speaker, en in split_speakers(text, profile["speakers"]):
        color = None
        if speaker:
            known = profile["speakers"].get(speaker)
            if known is None and speaker not in new:
                new.append(speaker)
            color = (known or {}).get("color") or getattr(text, "name_colors", {}).get(speaker) or profile["style"]["nameColor"]
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
    text_box: tuple | None = None  # gösterilen İngilizce satırın bölgedeki konumu (OCR'dan)
    pending_box: tuple | None = None  # ((x,y,w,h), satır) — görünen ama henüz çevrilmemiş yeni satır: hemen kapatılır
    diff_frames: int = 0  # gösterilen satırdan farklı okunan ardışık kare sayısı (OCR titremesine karşı)
    empty_frames: int = 0  # yazı okunamayan ardışık kare sayısı
    known_names: set = field(default_factory=set)  # cümle ortasında görülen isimler: cümle başında da korunur
    on_frame: Callable | None = None  # her karede kaynak dikdörtgeniyle (ya da None) çağrılır: katman konumu
    seen_t: float = 0.0  # yeni satırın ekranda ilk görüldüğü an
    hold: float = 0.0  # gösterilen çevirinin gecikmesi: altyazı gidince bu kadar daha kalır
    hide_at: float | None = None  # altyazı gitti, çeviri bu anda kalkacak
    translating: bool = False  # altyazı çevriliyor: ek bölgeler beklesin (altyazı öncelikli)
    extras: dict = field(default_factory=dict)  # ek bölge anahtarı -> Extra
    extra_engine: Any = None  # ek bölgelerin ayrı OCR motoru (altyazı döngüsüyle aynı anda okur)
    on_extras: Callable | None = None  # (rect, [(anahtar, bölge, Extra, görüntü)]) — ek bölge kutuları
    status: dict = field(default_factory=lambda: {"window": False, "last": None, "avgMs": None,
                                                  "slow": False, "error": None, "running": True})


def _translator(rt: Runtime) -> Callable[[str], str]:
    def tr(en: str) -> str:
        if not rt.model_ready:  # model inerken Ollama'ya istek gönderme (404 döner); İngilizce göster
            rt.status["error"] = "Çeviri modeli hazır değil; hazır olunca çeviri başlar. Şimdilik İngilizce gösteriliyor."
            raise RuntimeError("model hazır değil")
        try:
            rt.known_names.update(rt.profile["speakers"])
            out = translate(en, rt.settings["model"], rt.profile["glossary"], rt.cache, known=rt.known_names,
                            context=profile_context(rt.profile, en))
            rt.status["error"] = None
            return out
        except Exception as e:
            rt.status["error"] = f"Çeviri hatası: {e}"
            raise
    return tr


async def _source(rt: Runtime, profile: dict):
    """(dikdörtgen, PS5 karesi). PS5'te dikdörtgen kare koordinatıdır (0, 0, genişlik, yükseklik).
    Pencere kapalı/küçültülmüş ya da PS5 bağlanıyorsa dikdörtgen None."""
    if profile["source"] == ps5.SOURCE:
        frame = await asyncio.to_thread(ps5.stream.latest, rt.settings.get("ps5Host", ""))
        return ((0, 0, *frame.size) if frame is not None else None), frame
    return target_rect(profile["source"]), None


async def run(rt: Runtime, interval: float = 0.1) -> None:
    state = {"prev": None, "sent": ""}
    tr = _translator(rt)
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


def _track_cover(rt: Runtime, state: dict, text) -> None:
    """Kapağın nerede ve ne zaman olacağına karar verir (çeviri beklenmeden).
    - Ekranda Türkçe yokken yeni satır: ilk karede kapat.
    - Türkçe gösterilirken farklı okuma: ancak 2 kare üst üste sürerse yeni satır say (OCR titremesi/yarım okuma).
    - Aynı satır sürdükçe kutu yalnızca büyür (belirirken yarım okunan kareler küçültmez).
    - Boş kareler kapağı değiştirmez; satırın silinmesine stable() karar verir."""
    box = getattr(text, "box", None)
    if not (text and box):
        rt.empty_frames += 1
        if rt.empty_frames >= 2:  # yazı gitti: çevrilmemiş boş kapak da kalksın (yoksa boş kutu asılı kalıyordu)
            rt.pending_box = None
        return
    rt.empty_frames = 0
    if state["sent"] and _same(text, state["sent"]):
        rt.diff_frames = 0
        rt.pending_box = None
        rt.text_box = _union(rt.text_box, box)
        return
    rt.diff_frames += 1
    if not rt.last_lines or rt.diff_frames >= 2:
        if rt.pending_box is None:
            rt.seen_t = time.monotonic() - (0.1 * (rt.diff_frames - 1) if rt.last_lines else 0)
        prev = rt.pending_box[0] if rt.pending_box else None
        rt.pending_box = (_union(prev, box), getattr(text, "lines", 0))


def _clear(rt: Runtime, state: dict) -> None:
    rt.hide_at = None
    rt.text_box = None
    rt.pending_box = None
    if rt.last_lines:  # eski altyazı TV'de asılı kalmasın
        rt.last_lines = []
        rt.emit({"type": "lines", "lines": []})
    state.update(prev=None, sent="")


async def _frame(rt: Runtime, sct, state: dict, tr, t0: float) -> None:
    rt.status["running"] = rt.settings.get("running", True)
    if not rt.status["running"]:  # kullanıcı durdurdu: okuma yapma, ama pencere durumunu göster
        if rt.profile["source"] == ps5.SOURCE:  # PS5'e durmuşken bağlanma; bölge seçimi için açıldıysa bir süre sonra kapat
            ps5.stream.stop_if_idle()
            rt.status["window"] = ps5.stream.connected
        else:
            rt.status["window"] = target_rect(rt.profile["source"]) is not None
        _clear(rt, state)
        if rt.on_frame:
            rt.on_frame(None)
        await asyncio.sleep(0.3)
        return
    profile = rt.profile  # panel her an değiştirebilir; her karede yeniden okunur
    rect, frame = await _source(rt, profile)
    rt.status["window"] = rect is not None
    rt.status["ps5Error"] = ps5.stream.error if profile["source"] == ps5.SOURCE else None
    if rect is None:  # pencere kapandı/küçüldü ya da PS5 bağlanıyor
        _clear(rt, state)
        if rt.on_frame:
            rt.on_frame(None)
        await asyncio.sleep(1)
        return
    box = to_pixels(profile["region"], rect)
    shot = ps5.crop(frame, box) if frame is not None else grab(sct, box)
    t1 = time.perf_counter()
    region_img = Image.frombytes("RGB", shot.size, shot.rgb) if shot is not None and rt.on_frame else None
    rt.known_names.update(rt.profile["speakers"])
    text = await ocr(rt.engine, shot, rt.known_names, bool(profile.get("speakerColor")))
    text, score = clean(text, rt.known_names) if text else (text, 0.0)
    if text and score < GARBAGE_BELOW:  # çöp okuma ("2LİÇJ3"): çevirme, boş kare say
        text = type(text)("") if hasattr(text, "box") else ""
    t2 = time.perf_counter()
    _track_cover(rt, state, text)
    if rt.on_frame:
        rt.on_frame(rect, region_img)
    line = stable(state, text, score)
    if rt.hide_at and time.monotonic() >= rt.hide_at:  # okuma süresi doldu: çeviriyi kaldır
        rt.hide_at, rt.last_lines, rt.text_box = None, [], None
        rt.emit({"type": "lines", "lines": []})
        if rt.on_frame:
            rt.on_frame(rect, region_img)
    if line is None:
        return
    if not line:  # altyazı gitti: okunabilsin diye çeviri, gelirken geciktiği kadar daha kalsın
        if rt.last_lines and rt.hide_at is None:
            rt.hide_at = time.monotonic() + min(HOLD_MAX, max(HOLD_MIN, rt.hold))
        return
    rt.translating = True
    try:
        lines, new = await asyncio.to_thread(build_lines, line, profile, tr)
    finally:
        rt.translating = False
    t3 = time.perf_counter()
    if not any(l["tr"] for l in lines):  # model çeviremedi (açıklama yazdı): satır hiç gösterilmez
        rt.pending_box = None
        return
    rt.last_lines = lines
    rt.hide_at = None
    rt.hold = time.monotonic() - rt.seen_t if rt.seen_t else 0.0
    rt.text_box = _union(rt.pending_box[0] if rt.pending_box else None, getattr(line, "box", None))
    rt.pending_box = None
    rt.diff_frames = 0
    rt.emit({"type": "lines", "lines": lines})
    if rt.on_frame:
        rt.on_frame(rect, region_img)
    # Yeni konuşmacılar döngü iş parçacığında eklenir (panel komutlarıyla yarışmasın);
    # panel bu arada profili değiştirdiyse eski profile yazılmaz.
    seen = getattr(line, "name_colors", {})
    colorless = [n for n, c in seen.items() if n in profile["speakers"] and not profile["speakers"][n].get("color")]
    if (new or colorless) and rt.profile is profile:
        for name in new:
            profile["speakers"].setdefault(name, {"color": seen.get(name), "voice": None})
        for name in colorless:  # oyunun kendi isim rengi: panelden değiştirilebilir
            profile["speakers"][name]["color"] = seen[name]
        store.save_profile(profile)
    if line:
        rt.timings.append(round(1000 * (t3 - t0)))
        avg = round(sum(rt.timings) / len(rt.timings))
        rt.status.update(last={"capture": round(1000 * (t1 - t0)), "ocr": round(1000 * (t2 - t1)),
                               "translate": round(1000 * (t3 - t2))},
                         avgMs=avg, slow=avg > SLOW_MS, lastLine={"en": line, "lines": lines})


@dataclass
class Extra:
    """Bir ek bölgenin durumu: altyazıdan bağımsız sabitleme ve son çeviri."""
    state: dict = field(default_factory=lambda: {"prev": None, "sent": ""})
    lines: list = field(default_factory=list)
    box: tuple | None = None  # yazının bölgedeki konumu (OCR'dan)


def extra_key(r: dict) -> str:
    """Bölge adı ya da yeri değişince durumu sıfırlansın diye ikisinden oluşur."""
    return f"{r['name']}|{list(r['region'])}"


async def run_extras(rt: Runtime, interval: float = EXTRA_INTERVAL) -> None:
    """Ek bölgeler: yavaş döngü, öncelik sırasıyla (listedeki sıra). Altyazı çevrilirken ya da yeni altyazı
    belirmişken çeviriye başlamaz; altyazı hiç beklemez."""
    tr = _translator(rt)
    with mss.MSS() as sct:
        while True:
            await asyncio.sleep(interval)
            try:
                await _extras_frame(rt, sct, tr)
            except Exception as e:  # ek bölgedeki hata altyazıyı durdurmasın
                rt.status["error"] = f"Ek bölge okuma hatası: {e}"
                await asyncio.sleep(ERROR_PAUSE)


async def _extras_frame(rt: Runtime, sct, tr) -> None:
    profile = rt.profile
    regions = profile.get("extraRegions") or []
    rect, frame = None, None
    if regions and rt.settings.get("running", True) and (rt.extra_engine or rt.engine) is not None:
        rect, frame = await _source(rt, profile)
    if rect is None:
        rt.extras.clear()
        if rt.on_extras:
            rt.on_extras(None, [])
        return
    keys = [extra_key(r) for r in regions]
    rt.extras = {k: rt.extras.get(k) or Extra() for k in keys}
    items = []
    for key, r in zip(keys, regions):
        ex = rt.extras[key]
        box = to_pixels(r["region"], rect)
        shot = ps5.crop(frame, box) if frame is not None else grab(sct, box)
        img = Image.frombytes("RGB", shot.size, shot.rgb) if shot is not None and rt.on_extras else None
        text = await ocr(rt.extra_engine or rt.engine, shot, rt.known_names)
        text, score = clean(text, rt.known_names) if text else (text, 0.0)
        if text and score < GARBAGE_BELOW:
            text = ""
        line = stable(ex.state, text, score)
        if line is not None:
            if line:
                for _ in range(int(SUB_WAIT / 0.05)):  # altyazı öncelikli
                    if not (rt.translating or rt.pending_box):
                        break
                    await asyncio.sleep(0.05)
                try:
                    out = await asyncio.to_thread(tr, str(line))
                except Exception:  # Ollama kapalı / model yok: İngilizcesini göster
                    out = str(line)
                ex.lines = [{"speaker": None, "color": None, "en": str(line), "tr": out}]
            else:
                ex.lines = []
            ex.box = getattr(line, "box", None)
        items.append((key, r["region"], ex, img))
    if rt.on_extras:
        rt.on_extras(rect, items)
