"""PS5'ten doğrudan görüntü (Remote Play, pyremoteplay): eşleştirme + son kareyi verme. chiaki-ng gerekmez.

Yalnız görüntü alınır (oyun TV'de oynanır): ses ve kumanda kullanılmaz. Oturum kendi olay döngüsünde,
ayrı iş parçacığında çalışır (aynı döngüde uygulamanın döngüsünü kilitliyordu). PS5 aynı anda tek Remote Play
oturumuna izin verir: chiaki-ng açıkken bağlanılamaz.
"""
import asyncio
import logging
import threading
import time

from PIL import Image

SOURCE = "ps5"
IDLE_STOP = 60  # çeviri durmuşken bu kadar sn kare istenmezse bağlantı kapanır (PS5 boşuna meşgul kalmasın)
RETRY = 5       # bağlantı koptuysa yeniden deneme aralığı (sn)

_log = logging.getLogger(__name__)


def _patch_av() -> None:
    """pyremoteplay eski PyAV adlarını kullanıyor (Flags.LOW_DELAY); yeni PyAV'de küçük harf."""
    import av.codec.context as c
    for enum, old, new in ((c.Flags, "LOW_DELAY", "low_delay"), (c.Flags2, "FAST", "fast")):
        if not hasattr(enum, old) and hasattr(enum, new):
            setattr(enum, old, getattr(enum, new))


class Shot:
    """OCR ve katmanın beklediği yakalama nesnesi (mss sonucu gibi): width/height/size, rgb, bgra."""

    def __init__(self, img: Image.Image):
        self.img = img
        self.width, self.height = img.size
        self.size = img.size

    @property
    def rgb(self) -> bytes:
        return self.img.tobytes()

    @property
    def bgra(self) -> bytes:
        return self.img.convert("RGBA").tobytes("raw", "BGRA")


def crop(img: Image.Image, box: dict) -> Shot:
    """box: capture.to_pixels sonucu (kare koordinatında, rect=(0,0,W,H))."""
    l, t = box["left"], box["top"]
    return Shot(img.crop((l, t, l + box["width"], t + box["height"])))


# --- hesap ve eşleştirme ---

def account() -> str | None:
    from pyremoteplay import RPDevice
    names = RPDevice.get_profiles().usernames
    return names[0] if names else None


def login_url() -> str:
    from pyremoteplay.oauth import get_login_url
    return get_login_url()


def add_account(redirect_url: str) -> str:
    from pyremoteplay import RPDevice
    from pyremoteplay.oauth import get_user_account
    from pyremoteplay.profile import format_user_account
    if "code=" not in redirect_url:
        raise ValueError("Adres eksik: giriş sonrası açılan sayfanın adresini (code=… içeren) tamamen kopyalayın")
    user = format_user_account(get_user_account(redirect_url.strip()))
    if user is None:
        raise ValueError("PSN hesabı okunamadı; giriş adresini yeniden açıp tekrar deneyin")
    profiles = RPDevice.get_profiles()
    profiles.update_user(user)
    profiles.save()
    return user.name


def status(host: str) -> dict | None:
    """PS5'in durumu (ad, açık/dinlenme); ulaşılamazsa None."""
    from pyremoteplay import RPDevice
    if not host:
        return None
    d = RPDevice(host)
    if not d.get_status():
        return None
    user = account()
    return {"name": d.host_name, "on": d.is_on, "paired": bool(user and user in d.get_users())}


def pair(host: str, pin: str) -> str:
    from pyremoteplay import RPDevice
    user = account()
    if not user:
        raise ValueError("Önce PSN hesabıyla giriş yapın")
    pin = "".join(ch for ch in pin if ch.isdigit())
    if len(pin) != 8:
        raise ValueError("PIN 8 rakam olmalı")
    d = RPDevice(host)
    if not d.get_status():
        raise ValueError(f"{host} adresinde PS5 yanıt vermiyor (PS5 açık mı, IP doğru mu?)")
    if not d.register(user, pin):
        raise ValueError("Eşleştirme başarısız: PS5'te yeni kod alıp tekrar deneyin")
    return d.host_name


# --- görüntü akışı ---

class Stream:
    """Tek PS5 oturumu. latest() son kareyi (PIL, RGB) verir; gerekirse bağlantıyı başlatır."""

    def __init__(self):
        self.host = ""
        self.error: str | None = None
        self._device = None
        self._receiver = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connecting = False
        self._last_try = 0.0
        self._last_use = 0.0
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        s = self._device.session if self._device else None
        return bool(s and s.is_running)

    def latest(self, host: str) -> Image.Image | None:
        self._last_use = time.monotonic()
        if host != self.host:
            self.stop()
            self.host = host
        if not self.connected:
            self._start()
            return None
        frame = self._receiver.get_latest_video_frame() if self._receiver else None
        return frame.to_image() if frame is not None else None

    def wait_frame(self, host: str, timeout: float = 15) -> Image.Image | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            img = self.latest(host)
            if img is not None:
                return img
            time.sleep(0.3)
        return None

    def stop_if_idle(self) -> None:
        if self._device and time.monotonic() - self._last_use > IDLE_STOP:
            self.stop()

    def stop(self) -> None:
        with self._lock:
            dev, loop = self._device, self._loop
            self._device = self._receiver = None
        if dev and loop:
            loop.call_soon_threadsafe(dev.disconnect)

    def _start(self) -> None:
        with self._lock:
            if self._connecting or not self.host or time.monotonic() - self._last_try < RETRY:
                return
            self._connecting, self._last_try = True, time.monotonic()
        threading.Thread(target=self._connect, daemon=True, name="ps5-connect").start()

    def _connect(self) -> None:
        try:
            _patch_av()
            from pyremoteplay import RPDevice
            from pyremoteplay.receiver import QueueReceiver
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(target=self._loop.run_forever, daemon=True, name="ps5-session").start()
            user = account()
            if not user:
                raise RuntimeError("PS5 eşleştirilmemiş (Bağlantı sekmesi)")
            dev, rec = RPDevice(self.host), QueueReceiver(max_frames=2)
            if not dev.get_status():
                raise RuntimeError(f"PS5'e ulaşılamıyor ({self.host})")
            if user not in dev.get_users():
                raise RuntimeError("Bu PS5 eşleştirilmemiş (Bağlantı sekmesi)")

            async def go():
                # fps "low" = 30: OCR saniyede ~10 kare okur; 60 kare yalnız işlemci harcar
                dev.create_session(user, loop=self._loop, receiver=rec, resolution="1080p", fps="low")
                return await dev.connect() and await dev.async_wait_for_session(20)

            if not asyncio.run_coroutine_threadsafe(go(), self._loop).result(40):
                self._loop.call_soon_threadsafe(dev.disconnect)
                raise RuntimeError("PS5 oturumu açılamadı (chiaki-ng ya da PS uygulaması bağlı olabilir)")
            with self._lock:
                self._device, self._receiver = dev, rec
            self.error = None
        except Exception as e:  # noqa: BLE001 — durum panelde gösterilir, döngü yeniden dener
            _log.warning("PS5 bağlantısı: %s", e)
            self.error = str(e)
        finally:
            self._connecting = False


stream = Stream()
