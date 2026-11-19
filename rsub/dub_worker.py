"""Dublaj işçisi: ayrı Python ortamında (torch, chatterbox-tts, demucs, soundcard) çalışır.

Uygulamayla stdin/stdout üzerinden satır satır JSON konuşur; ağır bağımlılıklar uygulamanın kendisine girmez,
işçi çökse de altyazı sürer. Komutlar:
  {"op": "warm"}                                          → {"ready": true} model yüklendi
  {"op": "say", "id", "text", "conds": yol|None, "gain"}   → {"id", "wav": yol, "ms"}
  {"op": "listen", "on": bool}                            → (yanıt yok) oyun sesini halka belleğe kaydet / dur
  {"op": "clip", "speaker", "start", "end", "out"}        → {"sampled": ad, "seconds"} ya da {"cloned": ad, "out"}
Zamanlar time.time() (iki süreçte de aynı saat).
"""
import json
import os
import sys
import tempfile
import threading
import time
from collections import deque

import torch  # noqa: F401 — önce: soundfile vb. önce yüklenince Windows'ta c10.dll açılmıyor (WinError 1114)
import numpy as np

SAMPLE_SECONDS = 10.0  # klon için toplanan konuşma (Chatterbox ilk 10 sn'yi kullanır)
REC_SR = 44100
RING_SECONDS = 30


OUT = sys.stdout  # protokol kanalı; kütüphanelerin print'leri stderr'e gider, JSON satırlarını bozmasın
sys.stdout = sys.stderr


def send(msg: dict) -> None:
    OUT.write(json.dumps(msg, ensure_ascii=False) + "\n")
    OUT.flush()


class Recorder:
    """Varsayılan hoparlörün sesini (WASAPI loopback) son RING_SECONDS saniyelik halka belleğe yazar."""

    def __init__(self):
        self.on = False
        self.blocks: deque = deque()  # (bitiş zamanı, mono float32 blok)
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        import soundcard as sc
        while True:
            if not self.on:
                time.sleep(0.2)
                continue
            mic = sc.get_microphone(str(sc.default_speaker().name), include_loopback=True)
            with mic.recorder(samplerate=REC_SR, channels=2) as rec:
                while self.on:
                    data = rec.record(numframes=REC_SR // 10)
                    with self.lock:
                        self.blocks.append((time.time(), data.mean(axis=1).astype(np.float32)))
                        while self.blocks and self.blocks[0][0] < time.time() - RING_SECONDS:
                            self.blocks.popleft()

    def cut(self, start: float, end: float) -> np.ndarray:
        with self.lock:
            parts = [b for t, b in self.blocks if start <= t - len(b) / REC_SR and t <= end + 0.05]
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)


class Worker:
    def __init__(self):
        self.model = None
        self.conds: dict = {}  # yol -> Conditionals (her karakterin sesi bir kez yüklenir)
        self.samples: dict = {}  # karakter -> [ses parçaları]
        self.rec = Recorder()

    def tts(self):
        if self.model is None:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            self.model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
            self.default = self.model.conds
            # Modelin ses sınırı sabit 1000 birim (~40 sn): kısa metinde susmayı kaçırıp uzun anlamsız ses üretiyordu
            # ("Siktir git!" → 3,3 sn). Sınır metin uzunluğuna göre (cap) konur.
            orig = self.model.t3.inference
            self.model.t3.inference = lambda *a, **k: orig(*a, **{**k, "max_new_tokens": self.cap})
            send({"ready": True})
        return self.model

    cap = 1000

    def generate(self, text: str):
        """25 ses birimi/sn; en yavaş konuşma ~8 harf/sn + 0,8 sn pay (ölçüm: kısa replikler 1-2 sn'de biter)."""
        self.cap = int(25 * (len(text) / 8 + 0.8))
        return self.tts().generate(text, language_id="tr", cfg_weight=0.3)

    def say(self, msg):
        import soundfile
        from chatterbox.mtl_tts import Conditionals
        t0 = time.perf_counter()
        m = self.tts()
        path = msg.get("conds")
        if path and os.path.exists(path):
            if path not in self.conds:
                self.conds[path] = Conditionals.load(path, map_location="cuda")
            m.conds = self.conds[path]
        else:
            m.conds = self.default
        wav = self.generate(msg["text"]) * float(msg.get("gain", 1.0))
        fd, out = tempfile.mkstemp(suffix=".wav", prefix="rsub-dub-")
        os.close(fd)
        soundfile.write(out, wav.clamp(-1, 1).squeeze(0).cpu().numpy(), m.sr, subtype="PCM_16")
        send({"id": msg["id"], "wav": out, "ms": round(1000 * (time.perf_counter() - t0))})

    def clip(self, msg):
        name = msg["speaker"]
        part = self.rec.cut(msg["start"], msg["end"])
        if len(part) < REC_SR * 0.5:
            return
        got = self.samples.setdefault(name, [])
        got.append(part)
        seconds = sum(len(p) for p in got) / REC_SR
        if seconds < SAMPLE_SECONDS:
            send({"sampled": name, "seconds": round(seconds, 1)})
            return
        self.samples.pop(name)
        send({"sampled": name, "seconds": round(seconds, 1), "cloning": True})
        self.clone(name, np.concatenate(got), msg["out"])

    def clone(self, name, audio, out):
        """Bir kez: Demucs ile müzik/efekt ayıklanır, kalan konuşmadan ses koşulu hesaplanıp kaydedilir."""
        import soundfile
        import torch
        import demucs.api
        sep = demucs.api.Separator(model="htdemucs", device="cuda", segment=7)
        wav = torch.from_numpy(audio).unsqueeze(0).repeat(2, 1)
        _, stems = sep.separate_tensor(wav, REC_SR)
        vocals, sr = stems["vocals"].mean(dim=0, keepdim=True).cpu(), sep.samplerate
        del sep
        torch.cuda.empty_cache()
        os.makedirs(os.path.dirname(out), exist_ok=True)
        ref = out[:-3] + ".wav"
        soundfile.write(ref, vocals.squeeze(0).numpy(), sr, subtype="PCM_16")
        m = self.tts()
        m.prepare_conditionals(ref, exaggeration=0.5)
        m.conds.save(out)
        self.conds[out] = m.conds
        m.conds = self.default
        send({"cloned": name, "out": out})


def main():
    w = Worker()
    send({"started": True})
    for raw in sys.stdin:
        try:
            msg = json.loads(raw)
            if msg["op"] == "warm":  # yükle ve bir kez üret: ekran kartının ilk üretim ısınması ilk repliğe düşmesin
                w.generate("Hazır.")
            elif msg["op"] == "say":
                w.say(msg)
            elif msg["op"] == "listen":
                w.rec.on = bool(msg["on"])
            elif msg["op"] == "clip":
                w.clip(msg)
        except Exception as e:  # tek iş hatası işçiyi öldürmesin
            send({"id": msg.get("id") if isinstance(msg, dict) else None, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
