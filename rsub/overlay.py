"""Kaynak pencerenin üstünde, orijinal altyazıyı kapatan saydam katman.

Win32 katmanlı pencere (piksel bazında saydamlık). Özellikleri:
- her zaman en üstte, odak almaz, görev çubuğunda görünmez
- fare tıklamaları içinden geçer (altındaki oyun/video engellenmez)
- ekran yakalamaya görünmez (WDA_EXCLUDEFROMCAPTURE) → OCR kendi çevirimizi okumaz
Kendi iş parçacığında mesaj döngüsüyle çalışır; show/hide/close herhangi bir iş parçacığından çağrılabilir.
"""
import ctypes
import queue
import threading
from ctypes import wintypes

import numpy as np

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
# HWND 64 bit: tür verilmezse ctypes 32 bit int'e sığdırmaya çalışıp taşar
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p, wintypes.HDC,
                                       ctypes.c_void_p, wintypes.COLORREF, ctypes.c_void_p, wintypes.DWORD]
user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.HANDLE,
                                   wintypes.DWORD]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
user32.GetDC.argtypes = [wintypes.HWND]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

WS_POPUP = 0x80000000
WS_EX = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000  # LAYERED|TRANSPARENT|TOPMOST|TOOLWINDOW|NOACTIVATE
WDA_EXCLUDEFROMCAPTURE = 0x11
WM_APP, WM_DESTROY = 0x8000, 0x0002
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOMOVE_NOSIZE_NOACTIVATE = 0x0002 | 0x0001 | 0x0010


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


def _premultiplied_bgra(img) -> bytes:
    a = np.asarray(img.convert("RGBA"), dtype=np.uint16)
    alpha = a[..., 3:4]
    rgb = (a[..., :3] * alpha + 127) // 255
    return np.concatenate([rgb[..., ::-1], alpha], axis=-1).astype(np.uint8).tobytes()  # RGB → BGR


class Overlay:
    _class_registered = False
    _proc = None

    def __init__(self):
        self.hwnd = None
        self._q: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        threading.Thread(target=self._loop, name="overlay", daemon=True).start()
        self._ready.wait(5)

    # --- herhangi bir iş parçacığından ---
    def show(self, box: dict, img) -> None:
        self._post(("show", box, img))

    def hide(self) -> None:
        self._post(("hide",))

    def close(self) -> None:
        self._post(("close",))

    def _post(self, cmd) -> None:
        if self.hwnd:
            self._q.put(cmd)
            user32.PostMessageW(self.hwnd, WM_APP, 0, 0)

    # --- katman iş parçacığı ---
    def _loop(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        if not Overlay._class_registered:
            Overlay._proc = WNDPROC(self._wndproc_static)
            wc = WNDCLASSW(lpfnWndProc=Overlay._proc, hInstance=hinst, lpszClassName="rsub-overlay")
            user32.RegisterClassW(ctypes.byref(wc))
            Overlay._class_registered = True
        self.hwnd = user32.CreateWindowExW(WS_EX, "rsub-overlay", "rsub-overlay", WS_POPUP, 0, 0, 1, 1,
                                           None, None, hinst, None)
        _instances[self.hwnd] = self
        user32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE)
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    @staticmethod
    def _wndproc_static(hwnd, msg, wparam, lparam):
        inst = _instances.get(hwnd)
        if inst and msg == WM_APP:
            inst._drain()
            return 0
        if msg == WM_DESTROY:
            _instances.pop(hwnd, None)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _drain(self) -> None:
        while True:
            try:
                cmd = self._q.get_nowait()
            except queue.Empty:
                return
            if cmd[0] == "show":
                self._paint(cmd[1], cmd[2])
                user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
                user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE_NOSIZE_NOACTIVATE)
            elif cmd[0] == "hide":
                user32.ShowWindow(self.hwnd, SW_HIDE)
            elif cmd[0] == "close":
                user32.DestroyWindow(self.hwnd)
                return

    def _paint(self, box: dict, img) -> None:
        w, h = img.size
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bmi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                               biBitCount=32, biCompression=0)
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(mem, hbmp)
        data = _premultiplied_bgra(img)
        ctypes.memmove(bits, data, len(data))
        blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wintypes.POINT(box["left"], box["top"])),
                                   ctypes.byref(wintypes.SIZE(w, h)), mem, ctypes.byref(wintypes.POINT(0, 0)),
                                   0, ctypes.byref(blend), 2)  # ULW_ALPHA
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


_instances: dict = {}
