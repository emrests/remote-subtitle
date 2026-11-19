"""Sesli dublaj, uygulama tarafı: işçi süreci (dub_worker.py, ayrı Python ortamında) yönetir, kuyruğu tutar, çalar.

Ağır bağımlılık yok: çalma stdlib winsound ile, süre wave ile. Kuyruk kuralı: çalan ses biter; bekleyen en fazla
bir satır olur, yenisi gelirse bekleyenin yerine geçer (eski replik geç gelip yeni sahneye karışmasın).
Karakter sesi bir kez klonlanır: sesi olmayan karakter konuşurken oyun sesi kaydedilir, ~10 sn dolunca işçi klonlar,
dosyası profile yazılır ve kayıt o karakter için bir daha açılmaz.
"""
import hashlib
import json
import os
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Callable

from . import store

ENV = Path(os.environ.get("LOCALAPPDATA", "")) / "remote-subtitle" / "dub"
PYTHON = ENV / "Scripts" / "python.exe"
WORKER = Path(__file__).with_name("dub_worker.py")
PREVIEW = "Merhaba, bu benim sesim. Böyle mi konuşuyorum?"


def available() -> bool:
    return PYTHON.exists() and WORKER.exists()


def voice_path(profile: str, speaker: str) -> Path:
    h = lambda s: hashlib.sha1(s.encode()).hexdigest()[:16]
    return store.home() / "voices" / h(profile) / (h(speaker) + ".pt")


def wav_seconds(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def play_pc(path: str) -> None:
    import winsound
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


_live: list = []  # çıkışta kapatılacak işçiler


def close_all() -> None:
    for d in _live:
        d.close()


class Dubber:
    def __init__(self, on_audio: Callable[[str, dict], None], on_event: Callable[[dict], None],
                 spawn: Callable | None = None, play: Callable[[str], None] = play_pc):
        self.on_audio = on_audio  # (wav yolu, iş) → TV'ye gönderme vb.
        self.on_event = on_event  # klonlandı / örnek toplandı bildirimleri
        self.spawn = spawn or (lambda: subprocess.Popen(
            [str(PYTHON), "-u", str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        self.play = play
        self.proc = None
        self.lock = threading.Lock()
        self.next_id = 1
        self.busy = False  # işçi bir satırı seslendiriyor
        self.pending: dict | None = None  # sıradaki tek satır
        self.jobs: dict = {}
        self.playing_until = 0.0
        self.played: list = []  # (başlangıç, bitiş): kendi sesimiz örneğe karışmasın
        self.listening = False
        self.status = {"ready": False, "error": None, "lastMs": None, "samples": {}}
        _live.append(self)

    # --- işçi ---
    def _send(self, msg: dict) -> None:
        if self.proc is None or self.proc.poll() is not None:
            self.proc = self.spawn()
            self.status["ready"] = False
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read(self, proc) -> None:
        for raw in proc.stdout:
            try:
                self.handle(json.loads(raw))
            except ValueError:
                continue
        self.status.update(ready=False, error="Dublaj işçisi kapandı")
        with self.lock:
            self.busy = False

    def handle(self, msg: dict) -> None:
        if msg.get("ready"):
            self.status.update(ready=True, error=None)
        elif "sampled" in msg:
            self.status["samples"][msg["sampled"]] = msg["seconds"]
            self.on_event(msg)
        elif "cloned" in msg:
            self.status["samples"].pop(msg["cloned"], None)
            self.on_event(msg)
        elif "id" in msg:
            job = self.jobs.pop(msg["id"], None)
            if "error" in msg:
                self.status["error"] = msg["error"]
            elif job:
                self.status.update(lastMs=msg["ms"], error=None)
                self._play(msg["wav"], job)
            with self.lock:
                self.busy = False
            self._pump()

    # --- seslendirme ---
    def say(self, text: str, conds: str | None, gain: float = 1.0, **job) -> None:
        with self.lock:
            self.pending = {"text": text, "conds": conds, "gain": gain, **job}
        self._pump()

    def _pump(self) -> None:
        with self.lock:
            if self.busy or not self.pending:
                return
            job, self.pending, self.busy = self.pending, None, True
            jid, self.next_id = self.next_id, self.next_id + 1
            self.jobs[jid] = job
        try:
            self._send({"op": "say", "id": jid, "text": job["text"], "conds": job["conds"], "gain": job["gain"]})
        except OSError as e:
            self.status["error"] = f"Dublaj başlatılamadı: {e}"
            with self.lock:
                self.busy = False

    def _play(self, wav: str, job: dict) -> None:
        now = time.time()
        start = max(now, self.playing_until)  # önceki bitmeden başlarsa winsound onu keser: sırayla
        dur = wav_seconds(wav)
        self.playing_until = start + dur
        self.played = [p for p in self.played if p[1] > now - 60] + [(start, start + dur)]

        def go():
            time.sleep(max(0.0, start - time.time()))
            if job.get("pc", True):
                self.play(wav)
            self.on_audio(wav, job)
        threading.Thread(target=go, daemon=True).start()

    # --- örnek toplama (karakter başına bir kez) ---
    def listen(self, on: bool) -> None:
        if on != self.listening:
            self.listening = on
            self._send({"op": "listen", "on": on})

    def clip(self, speaker: str, start: float, end: float, out: str) -> None:
        """Satırın görüldüğü aralığın oyun sesi o karaktere eklenir; o arada kendi dublajımız çaldıysa alınmaz."""
        if any(a < end and b > start for a, b in self.played):
            return
        self._send({"op": "clip", "speaker": speaker, "start": start, "end": end, "out": out})

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
