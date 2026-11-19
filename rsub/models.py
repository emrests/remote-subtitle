"""Çeviri modeli kataloğu, VRAM'e göre öneri ve Ollama üzerinden indirme."""
import json
import os
import subprocess
from pathlib import Path
import urllib.request
from typing import Callable

from .translate import OLLAMA

# İyiden kötüye. Boyut ve VRAM değerleri yaklaşık (4-bit, Ollama varsayılan sıkıştırma).
CATALOG = [
    {"id": "translategemma:27b", "label": "TranslateGemma 27B", "size_gb": 17, "min_vram_mb": 20000, "note": "En iyi kalite, en yavaş"},
    {"id": "translategemma:12b", "label": "TranslateGemma 12B", "size_gb": 8, "min_vram_mb": 10000, "note": "Kalite ve hız dengesi"},
    {"id": "gemma3:12b", "label": "Gemma 3 12B", "size_gb": 8, "min_vram_mb": 10000, "note": "Genel model, terim listesine daha iyi uyar"},
    {"id": "translategemma:4b", "label": "TranslateGemma 4B", "size_gb": 3.3, "min_vram_mb": 5000, "note": "Hızlı, düşük VRAM"},
]


def recommend(vram_mb: int | None) -> str:
    fits = [m["id"] for m in CATALOG if vram_mb and m["min_vram_mb"] <= vram_mb]
    return fits[0] if fits else CATALOG[-1]["id"]


def model_infos(vram_mb: int | None, installed_ids: set[str] = frozenset()) -> list[dict]:
    rec = recommend(vram_mb)
    return [{**m, "fits": bool(vram_mb) and m["min_vram_mb"] <= vram_mb, "recommended": m["id"] == rec,
             "installed": m["id"] in installed_ids} for m in CATALOG]


def gpu_vram_mb() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        return max(int(x) for x in out.stdout.split())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _get(path: str, timeout: float):
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=timeout) as r:
        return json.load(r)


def ollama_up() -> bool:
    try:
        _get("/api/version", 1)
        return True
    except Exception:  # 11434'te başka bir şey dinliyorsa da "Ollama yok" say
        return False


def installed() -> set[str]:
    try:
        return {m["name"] for m in _get("/api/tags", 3)["models"]}
    except Exception:
        return set()


def start_ollama() -> bool:
    """Ollama kurulu ama çalışmıyorsa arka planda başlatır (kullanıcı ayrıca açmak zorunda kalmasın)."""
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        for exe in (Path(base) / "Programs" / "Ollama" / "ollama.exe", Path(base) / "Ollama" / "ollama.exe"):
            if base and exe.is_file():
                subprocess.Popen([str(exe), "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    return False


OLLAMA_PROCESSES = ("ollama app.exe", "ollama.exe")  # önce tepsi uygulaması: yoksa sunucuyu yeniden başlatır


def stop_ollama() -> None:
    """Ollama'yı tamamen kapatır (tepsi uygulaması, sunucu ve model süreçleri)."""
    for name in OLLAMA_PROCESSES:
        subprocess.run(["taskkill", "/F", "/T", "/IM", name], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def pull(model: str, on_pct: Callable[[int], None]) -> None:
    """Ollama indirmeyi kaldığı yerden sürdürür; hata olursa exception fırlatır."""
    body = json.dumps({"model": model, "stream": True}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/pull", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        for line in r:
            msg = json.loads(line)
            if "error" in msg:
                raise RuntimeError(msg["error"])
            if msg.get("total"):
                on_pct(int(100 * msg.get("completed", 0) / msg["total"]))
    on_pct(100)
