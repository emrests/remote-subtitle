import ctypes
import time

import mss
from PIL import Image

from rsub.capture import set_dpi_aware
from rsub.overlay import Overlay

from rsub.overlay import user32  # argtypes'ı tanımlı (64 bit HWND)
BOX = {"left": 200, "top": 200, "width": 320, "height": 80}


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_overlay_shows_clickthrough_and_hides():
    set_dpi_aware()
    o = Overlay()
    try:
        o.show(BOX, Image.new("RGBA", (BOX["width"], BOX["height"]), (255, 0, 255, 255)))
        assert _wait(lambda: o.hwnd and user32.IsWindowVisible(o.hwnd))
        user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        ex = user32.GetWindowLongPtrW(o.hwnd, -20)  # GWL_EXSTYLE
        assert ex & 0x20 and ex & 0x80000 and ex & 0x8  # TRANSPARENT (tık geçer), LAYERED, TOPMOST
        aff = ctypes.c_uint(0)
        user32.GetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowDisplayAffinity(o.hwnd, ctypes.byref(aff))
        assert aff.value == 0x11  # WDA_EXCLUDEFROMCAPTURE
        o.hide()
        assert _wait(lambda: not user32.IsWindowVisible(o.hwnd))
    finally:
        o.close()


def test_overlay_is_invisible_to_screen_capture():
    set_dpi_aware()
    o = Overlay()
    try:
        o.show(BOX, Image.new("RGBA", (BOX["width"], BOX["height"]), (255, 0, 255, 255)))
        assert _wait(lambda: o.hwnd and user32.IsWindowVisible(o.hwnd))
        time.sleep(0.2)
        with mss.MSS() as s:
            px = s.grab(BOX).pixel(BOX["width"] // 2, BOX["height"] // 2)
        assert px != (255, 0, 255)  # OCR kendi çevirimizi okumaz
    finally:
        o.close()
