"""Windows'un yerleşik OCR motoru.

İngilizce dil paketi şart değil: Latin alfabeli herhangi bir OCR dili (Türkçe Windows'ta "tr" hazır gelir)
İngilizce altyazıyı da okur. RDR2 ölçümünde Türkçe paket 5/5 satırı birebir doğru okudu.
"""
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

# Latin alfabesiyle yazılan ve Windows OCR'ın desteklediği diller (önce İngilizce)
LATIN = ("en", "tr", "de", "fr", "es", "it", "pt", "nl", "pl", "cs", "sv", "da", "nb", "fi", "hu", "ro", "hr", "sk", "sl")


def _languages() -> list[str]:
    return [l.language_tag for l in OcrEngine.available_recognizer_languages]


def ocr_language() -> str | None:
    """Kullanılacak OCR dili; Latin alfabeli dil yoksa None."""
    langs = _languages()
    for prefix in LATIN:
        for tag in langs:
            if tag.split("-")[0].lower() == prefix:
                return tag
    return None


def make_ocr():
    lang = ocr_language()
    return OcrEngine.try_create_from_language(Language(lang)) if lang else None


class OcrText(str):
    """Okunan metin; .box = görüntüdeki kapsayıcı dikdörtgen (x, y, w, h) ya da None, .lines = satır sayısı."""
    box: tuple | None = None
    lines: int = 0


NAME_CONTRAST = 0.25  # isim ile replik parlaklığı arasındaki en az oran farkı (ölçüm: RDR2 isim 87, replik 167)


def mark_speaker(words: list[str], levels: list[float]) -> list[str]:
    """Satır başındaki 1-3 kelime cümlenin kalanından belirgin farklı renkteyse (RDR2: gri isim, beyaz replik)
    sonuncusuna ':' ekler; böylece "Dutch Arthur! Any luck?" → "Dutch: Arthur! ...". Sıradan altyazı değişmez."""
    if len(words) < 2 or words[0].endswith(":"):
        return words
    for n in (1, 2, 3):
        if n >= len(words):
            break
        rest = sorted(levels[n:])[len(levels[n:]) // 2]
        head = levels[:n]
        if not rest or not all(w[:1].isupper() for w in words[:n]):
            break
        if all(abs(h - rest) / rest > NAME_CONTRAST for h in head):
            if abs(levels[n] - rest) / rest > NAME_CONTRAST:
                continue  # bir sonraki kelime de isim rengi: ad daha uzun
            return words[:n - 1] + [words[n - 1] + ":"] + words[n:]
        break
    return words


def _levels(shot, words) -> list[float]:
    """Kelime başına yazı parlaklığı: kutudaki piksellerin 95. yüzdeliği (yazı, zeminden parlak)."""
    import numpy as np
    a = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)[..., :3].mean(axis=2)
    out = []
    for wd in words:
        r = wd.bounding_rect
        p = a[max(0, int(r.y)):int(r.y + r.height), max(0, int(r.x)):int(r.x + r.width)]
        out.append(float(np.percentile(p, 95)) if p.size else 0.0)
    return out


async def ocr(engine, shot, by_color: bool = False) -> OcrText:
    w = DataWriter()
    w.write_bytes(shot.bgra)
    bmp = SoftwareBitmap.create_copy_from_buffer(w.detach_buffer(), BitmapPixelFormat.BGRA8, shot.width, shot.height)
    result = await engine.recognize_async(bmp)
    if by_color:
        texts = [" ".join(mark_speaker([wd.text for wd in line.words], _levels(shot, line.words)))
                 for line in result.lines]
    else:
        texts = [line.text for line in result.lines]
    out = OcrText(" ".join(texts).strip())
    out.lines = sum(1 for line in result.lines if line.text.strip())
    rects = [wd.bounding_rect for line in result.lines for wd in line.words]
    if rects:
        x0, y0 = min(r.x for r in rects), min(r.y for r in rects)
        x1, y1 = max(r.x + r.width for r in rects), max(r.y + r.height for r in rects)
        out.box = (round(x0), round(y0), round(x1 - x0), round(y1 - y0))
    return out


class _Frame:
    def __init__(self, img):
        self.width, self.height = img.size
        self.bgra = img.convert("RGBA").tobytes("raw", "BGRA")


BRIGHT_SCALE, BRIGHT_THRESHOLD = 2, 195


def bright_text(shot):
    """Kutusuz, parlak zemin üstündeki yazı için (RDR2 görev yazısı karda): 2x büyüt, yalnız en parlak pikselleri
    siyah yazı olarak bırak. Ölçüm: normal okuma 'ffi' / boş, bu yöntem 'Get to the cliff edge'."""
    from PIL import Image
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    g = img.resize((img.width * BRIGHT_SCALE, img.height * BRIGHT_SCALE), Image.LANCZOS).convert("L")
    return _Frame(g.point(lambda v: 0 if v > BRIGHT_THRESHOLD else 255))


async def read_best(engine, shot, known: set[str], by_color: bool = False) -> "OcrText":
    """Önce normal okuma; zayıf ya da kısaysa (puan < 0,9 veya 3 kelimeden az) parlak-yazı yöntemiyle de oku,
    iyisini al. Normal altyazıda ikinci okuma çalışmaz."""
    from .cleanup import clean
    first = await ocr(engine, shot, by_color)
    s1 = clean(first, known)[1] if first else 0.0
    w1 = len(str(first).split())
    # tek kelimelik çöp ("ffi" → düzeltmeyle "fri") puanı kandırır: kısa okumada da ikinci yöntemi dene
    if (s1 >= 0.9 and w1 >= 3) or not hasattr(shot, "rgb"):
        return first
    second = await ocr(engine, bright_text(shot))
    s2 = clean(second, known)[1] if second else 0.0
    w2 = len(str(second).split())
    if not (s2 > s1 + 0.1 or (s2 >= 0.8 and w2 > w1)):
        return first
    if second.box:
        second.box = tuple(round(v / BRIGHT_SCALE) for v in second.box)
    return second
