"""Windows'un yerleşik OCR motoru."""
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter


def has_english() -> bool:
    return any(l.language_tag.startswith("en") for l in OcrEngine.available_recognizer_languages)


def make_ocr():
    if has_english():
        return OcrEngine.try_create_from_language(Language("en-US"))
    return OcrEngine.try_create_from_user_profile_languages()  # İngilizce paket yoksa doğruluk düşer


async def ocr(engine, shot) -> str:
    w = DataWriter()
    w.write_bytes(shot.bgra)
    bmp = SoftwareBitmap.create_copy_from_buffer(w.detach_buffer(), BitmapPixelFormat.BGRA8, shot.width, shot.height)
    result = await engine.recognize_async(bmp)
    return " ".join(line.text for line in result.lines).strip()
