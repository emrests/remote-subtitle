"""Çeviriyi bir dikdörtgene (orijinal altyazı bölgesi) sığdırıp RGBA görüntü olarak çizer.

Kaynağın üstündeki katman (overlay.py) bu görüntüyü gösterir. Bölge tamamen arka planla kaplanır,
böylece altındaki İngilizce altyazı görünmez.
"""
import os
import winreg
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
MIN_PX = 12
COVER_ALPHA = 0.92  # bölgeyi kapatmak için en az bu kadar opak (İngilizce altyazı alttan görünmesin)


@lru_cache(maxsize=64)
def font_path(name: str, bold: bool = False) -> str:
    want = f"{name} Bold" if bold else name
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        i = 0
        while True:
            try:
                label, file, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            base = label.split(" (")[0]
            if base == want or base.startswith(want + " &"):  # "Cambria & Cambria Math"
                return file if os.path.isabs(file) else os.path.join(FONTS_DIR, file)
    except OSError:
        pass
    if bold and name != "Segoe UI":
        return font_path(name, False)
    return os.path.join(FONTS_DIR, "segoeuib.ttf" if bold else "segoeui.ttf")


@lru_cache(maxsize=128)
def _font(name: str, bold: bool, px: int):
    return ImageFont.truetype(font_path(name, bold), px)


def _rgba(hex_color: str, alpha: float) -> tuple:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), round(255 * alpha)


def _rows(lines: list[dict], style: dict, px: int, max_w: int) -> list[dict]:
    """Kelime kelime sarar. Satır = [(metin, renk, kalın)] parçaları."""
    regular, bold = _font(style["font"], False, px), _font(style["font"], True, px)
    rows = []
    for line in lines:
        parts = []
        if line.get("speaker"):
            parts.append((line["speaker"] + ":", line.get("color") or style["nameColor"], True))
        parts += [(w, style["color"], False) for w in line["tr"].split()]
        row, width = [], 0
        for text, color, is_bold in parts:
            font = bold if is_bold else regular
            w = font.getlength(text + " ")
            if row and width + w > max_w:
                rows.append({"parts": row, "width": width})
                row, width = [], 0
            row.append((text, color, font))
            width += w
        if row:
            rows.append({"parts": row, "width": width})
    line_h = round(px * 1.25)
    for r in rows:
        r["width"] = round(r["width"] - regular.getlength(" "))
        r["height"] = line_h
    return rows


def fit(lines: list[dict], style: dict, box_w: int, box_h: int, scale: float) -> tuple[int, list[dict]]:
    """Ölçeklenmiş yazı boyutuyla başlar; sığmazsa küçültür. (yazı boyutu, satırlar) döner."""
    px = max(MIN_PX, round(style["size"] * scale))
    pad = max(4, round(box_w * 0.03))
    while True:
        rows = _rows(lines, style, px, box_w - 2 * pad)
        if (sum(r["height"] for r in rows) <= box_h and all(r["width"] <= box_w - 2 * pad for r in rows)) or px <= MIN_PX:
            return px, rows
        px = max(MIN_PX, int(px * 0.9))


def render(lines: list[dict], style: dict, w: int, h: int, scale: float):
    lines = [l for l in lines if l.get("tr")]
    if not lines or w < 4 or h < 4:
        return None
    img = Image.new("RGBA", (w, h), _rgba(style["bg"], max(style["bgOpacity"], COVER_ALPHA)))
    draw = ImageDraw.Draw(img)
    _, rows = fit(lines, style, w, h, scale)
    y = (h - sum(r["height"] for r in rows)) // 2
    for r in rows:
        x = (w - r["width"]) // 2
        for text, color, font in r["parts"]:
            draw.text((x, y), text, font=font, fill=_rgba(color, 1.0))
            x += font.getlength(text + " ")
        y += r["height"]
    return img
