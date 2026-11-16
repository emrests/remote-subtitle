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
    # Önce geçici dosyaya yaz, sonra tek adımda değiştir: yarıda kalan yazma eski dosyayı bozmasın
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _merge(default: dict, data) -> dict:
    """Saklanan değeri yalnızca türü varsayılanla uyuşuyorsa al (bozuk/eski dosyalar açılışı engellemesin)."""
    out = dict(default)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in default and (isinstance(v, type(default[k])) or (isinstance(default[k], float) and isinstance(v, int))):
                out[k] = v
    return out


def load_settings() -> dict:
    return _merge(DEFAULT_SETTINGS, _read(home() / "settings.json"))


def save_settings(s: dict) -> None:
    _write(home() / "settings.json", s)


def load_profile(name: str) -> dict:
    data = _read(_path(name))
    data = data if isinstance(data, dict) else {}
    p = _merge(default_profile(name), data)
    p["name"] = name
    p["style"] = _merge(DEFAULT_STYLE, data.get("style"))
    r = p["region"]
    if len(r) != 4 or not all(isinstance(v, (int, float)) for v in r):
        p["region"] = default_profile(name)["region"]
    p["glossary"] = {k: v for k, v in p["glossary"].items() if isinstance(v, str)}
    p["speakers"] = {k: {"color": v.get("color") if isinstance(v.get("color"), str) else None, "voice": v.get("voice")}
                     for k, v in p["speakers"].items() if isinstance(v, dict)}
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
