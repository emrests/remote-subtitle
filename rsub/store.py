"""Ayarlar ve oyun profilleri: %APPDATA%\\remote-subtitle altında JSON."""
import base64
import copy
import json
import os
from pathlib import Path

DEFAULT_SETTINGS = {"profile": "Varsayılan", "model": "translategemma:12b", "chiakiPath": ""}
DEFAULT_STYLE = {"font": "Segoe UI", "size": 48, "color": "#ffffff", "bg": "#000000", "bgOpacity": 0.75,
                 "position": "bottom", "offset": 60, "nameColor": "#ffd166"}


def home() -> Path:
    return Path(os.environ.get("RSUB_HOME") or Path(os.environ["APPDATA"]) / "remote-subtitle")


def default_profile(name: str) -> dict:
    return {"name": name, "source": "monitor:1", "region": [0.0, 0.7, 1.0, 0.3],
            "style": dict(DEFAULT_STYLE), "glossary": {}, "speakers": {}}


def _path(name: str) -> Path:
    # Dosya adı = adın base64'ü; böylece "Spider-Man: 2/b" gibi adlar da kaydedilebilir.
    return home() / "profiles" / (base64.urlsafe_b64encode(name.encode()).decode() + ".json")


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings() -> dict:
    return {**DEFAULT_SETTINGS, **(_read(home() / "settings.json") or {})}


def save_settings(s: dict) -> None:
    _write(home() / "settings.json", s)


def load_profile(name: str) -> dict:
    p = default_profile(name)
    data = _read(_path(name))
    if isinstance(data, dict):
        p.update({k: v for k, v in data.items() if k != "style"})
        p["style"].update(data.get("style") or {})
        p["name"] = name
    return p


def save_profile(p: dict) -> None:
    _write(_path(p["name"]), p)


def list_profiles() -> list[str]:
    d = home() / "profiles"
    names = [(_read(f) or {}).get("name") for f in d.glob("*.json")] if d.exists() else []
    return sorted(n for n in names if n)


def delete_profile(name: str) -> None:
    _path(name).unlink(missing_ok=True)


def copy_profile(name: str, new: str) -> dict:
    p = copy.deepcopy(load_profile(name))
    p["name"] = new
    save_profile(p)
    return p
