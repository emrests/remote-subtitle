"""Geliştirici modundaki Samsung TV ile konuşma (sdb): bulma, kimlik okuma, kurulum izni, kurma, başlatma.

Komutlar Tizen CLI'dan (tizen-new-cli: InstallCLICommand, InstallPermitCLICommand, SecureCmdVer4_0_device):
kurulum izni = device-profile.xml'i /home/developer'a göndermek; kurulum = paketi geçici klasöre gönderip
"0 appinstall <paket> <yol>" (eski TV: "0 vd_appinstall"); başlatma = "0 execute <uygulama>".
sdb.exe: uygulamayla gelen kopya (packaging/vendor) ya da kurulu Tizen Studio.
"""
from __future__ import annotations

import concurrent.futures as cf
import ipaddress
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

PORT = 26101          # geliştirici modundaki TV'nin sdb portu
PKG_ID = "RmSubTvApp"
APP_ID = "RmSubTvApp.RemoteSubtitle"
TMP_DIRS = ("/home/owner/share/tmp/sdk_tools/tmp", "/opt/usr/apps/tmp")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: komut penceresi yanıp sönmesin


def sdb_path() -> str | None:
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for p in (here / "sdb" / "sdb.exe", here / "packaging" / "vendor" / "sdb" / "sdb.exe",
              Path(os.environ.get("SystemDrive", "C:") + "\\") / "tizen-studio" / "tools" / "sdb.exe"):
        if p.exists():
            return str(p)
    return shutil.which("sdb")


def _run(args: list[str], timeout: float = 60) -> str:
    exe = sdb_path()
    if not exe:
        raise RuntimeError("sdb bulunamadı (TV ile konuşma aracı)")
    r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                       encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


run = _run  # testler sahtesini koyar


def serial(ip: str) -> str:
    return f"{ip}:{PORT}"


def scan(networks: list[str], timeout: float = 0.5) -> list[str]:
    """Verilen ağlarda (ör. "192.168.68.0/24") sdb portu açık cihazlar: geliştirici modundaki TV'ler."""
    hosts = [str(h) for n in networks for h in ipaddress.ip_network(n, strict=False).hosts()]

    def probe(ip):
        with socket.socket() as s:
            s.settimeout(timeout)
            return ip if s.connect_ex((ip, PORT)) == 0 else None

    with cf.ThreadPoolExecutor(128) as ex:
        return [ip for ip in ex.map(probe, hosts) if ip]


def connect(ip: str) -> None:
    out = run(["connect", ip], timeout=30)
    if "connected" not in out.lower():
        raise RuntimeError(f"TV'ye bağlanılamadı ({ip}). TV'de Geliştirici Modu açık ve Host PC IP bu bilgisayar mı?")


def info(ip: str) -> dict:
    """{"ip", "model", "duid"}; TV'ye bağlanır."""
    connect(ip)
    model = ""
    for line in run(["devices"]).splitlines():
        if line.startswith(serial(ip)):
            parts = line.split()
            model = parts[-1] if len(parts) >= 3 else ""
    duid = run(["-s", serial(ip), "shell", "0", "getduid"]).strip().splitlines()
    duid = duid[-1].strip() if duid else ""
    return {"ip": ip, "model": model, "duid": duid}


def shell(ip: str, *cmd: str, timeout: float = 120) -> str:
    return run(["-s", serial(ip), "shell", *cmd], timeout=timeout)


def push(ip: str, data: bytes, remote: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        local = Path(d) / Path(remote).name
        local.write_bytes(data)
        out = run(["-s", serial(ip), "push", str(local), remote], timeout=180)
    if "error" in out.lower() or "fail" in out.lower():
        raise RuntimeError(f"TV'ye dosya gönderilemedi: {out.strip()[:200]}")


def permit(ip: str, device_profile: bytes) -> None:
    """Tizen Studio'daki "Permit to install applications": sertifikanın TV listesini TV'ye bildirir."""
    push(ip, device_profile, "/home/developer/device-profile.xml")


def install(ip: str, wgt: bytes, pkg_id: str = PKG_ID) -> str:
    name = f"{pkg_id}.wgt"
    last = ""
    for tmp in TMP_DIRS:
        remote = f"{tmp}/{name}"
        try:
            push(ip, wgt, remote)
        except RuntimeError as e:
            last = str(e)
            continue
        for cmd in ("appinstall", "vd_appinstall"):
            out = shell(ip, "0", cmd, pkg_id, remote)
            if "install completed" in out.lower() or "100%" in out:
                return out
            last = out
            if "not found" not in out.lower() and "unknown" not in out.lower():
                break  # komut var ama kurulum başarısız: diğerini denemenin anlamı yok
    raise RuntimeError("Kurulum başarısız: " + _reason(last))


def _reason(out: str) -> str:
    low = out.lower()
    if "signature" in low or "certificate" in low or "author" in low:
        return "imza/sertifika reddedildi (TV kimliği sertifikada mı? Kurulum izni verildi mi?)"
    lines = [l for l in out.strip().splitlines() if l.strip()]
    return (lines[-1] if lines else "TV yanıt vermedi")[:200]


def launch(ip: str, app_id: str = APP_ID) -> None:
    shell(ip, "0", "execute", app_id, timeout=30)
