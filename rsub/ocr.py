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


async def ocr(engine, shot) -> OcrText:
    w = DataWriter()
    w.write_bytes(shot.bgra)
    bmp = SoftwareBitmap.create_copy_from_buffer(w.detach_buffer(), BitmapPixelFormat.BGRA8, shot.width, shot.height)
    result = await engine.recognize_async(bmp)
    out = OcrText(" ".join(line.text for line in result.lines).strip())
    out.lines = sum(1 for line in result.lines if line.text.strip())
    rects = [wd.bounding_rect for line in result.lines for wd in line.words]
    if rects:
        x0, y0 = min(r.x for r in rects), min(r.y for r in rects)
        x1, y1 = max(r.x + r.width for r in rects), max(r.y + r.height for r in rects)
        out.box = (round(x0), round(y0), round(x1 - x0), round(y1 - y0))
    return out
