"""Kaynak (pencere ya da monitör) bulma, oranlı bölgeyi piksele çevirme ve ekran yakalama."""
import ctypes
from ctypes import wintypes

import io

import mss
from PIL import Image

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
APP_TITLE = "remote-subtitle"
HIDDEN = {APP_TITLE, "Program Manager"}


def _cloaked(hwnd) -> bool:
    # Arka planda askıya alınmış UWP pencereleri "görünür" sayılır ama ekranda yoktur
    v = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), ctypes.sizeof(v))  # DWMWA_CLOAKED
    return bool(v.value)


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # monitör bazında DPI farkındalığı
    except (AttributeError, OSError):
        pass


def _windows() -> list[tuple[int, str]]:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value not in HIDDEN and not _cloaked(hwnd):
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def list_sources() -> list[dict]:
    with mss.MSS() as s:
        mons = [{"id": f"monitor:{i}", "label": f"Monitör {i} ({m['width']}×{m['height']})"}
                for i, m in enumerate(s.monitors[1:], start=1)]
    return mons + [{"id": title, "label": title} for _, title in _windows()]


def pick_window(windows: list[tuple[int, str]], source: str) -> int | None:
    """Önce birebir başlık, sonra başlık başı, en son içinde geçen; her kademede en kısa başlık
    (ör. "chiaki-ng" penceresi, "chiaki-ng releases - Google Chrome" sekmesinden önce). Boş kaynak eşleşmez."""
    want = source.strip().lower()
    if not want:
        return None
    by_len = sorted(windows, key=lambda w: len(w[1]))
    for test in (lambda t: t == want, lambda t: t.startswith(want), lambda t: want in t):
        for hwnd, title in by_len:
            if test(title.lower()):
                return hwnd
    return None


def target_rect(source: str) -> tuple[int, int, int, int] | None:
    """(left, top, width, height) sanal masaüstü pikselinde; bulunamazsa ya da küçültülmüşse None."""
    if source.startswith("monitor:"):
        with mss.MSS() as s:
            i = int(source.split(":")[1])
            if 1 <= i < len(s.monitors):
                m = s.monitors[i]
                return m["left"], m["top"], m["width"], m["height"]
        return None
    hwnd = pick_window(_windows(), source)
    if hwnd is None or user32.IsIconic(hwnd):
        return None
    r, p = wintypes.RECT(), wintypes.POINT(0, 0)
    user32.GetClientRect(hwnd, ctypes.byref(r))
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return (p.x, p.y, r.right, r.bottom) if r.right > 0 and r.bottom > 0 else None


def video_frame(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Pencere içindeki 16:9 oyun karesi (chiaki/YouTube pencere 16:9 değilse siyah şeritler hariç)."""
    L, T, W, H = rect
    if W * 9 > H * 16:  # pencere daha geniş: yanlarda şerit
        w = round(H * 16 / 9)
        return L + (W - w) // 2, T, w, H
    h = round(W * 9 / 16)
    return L, T + (H - h) // 2, W, h


def to_pixels(region: list[float], rect: tuple[int, int, int, int]) -> dict:
    x, y, w, h = region
    L, T, W, H = rect
    return {"left": L + round(x * W), "top": T + round(y * H),
            "width": max(1, round(w * W)), "height": max(1, round(h * H))}


def grab(sct, box: dict):
    return sct.grab(box)


def snapshot_jpeg(source: str) -> tuple[bytes, int, int] | None:
    """Bölge seçimi için anlık görüntü; JPEG, PNG'den ~10 kat küçük."""
    rect = target_rect(source)
    if not rect:
        return None
    with mss.MSS() as s:
        shot = s.grab(to_pixels([0, 0, 1, 1], rect))
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.thumbnail((1920, 1920))  # oranlar korunur; bölge oranlı saklandığı için çözünürlük önemsiz
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue(), shot.width, shot.height
