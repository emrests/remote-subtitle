# PyInstaller: python -m PyInstaller packaging/rsub.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "/.."

a = Analysis(
    [ROOT + "/rsub/__main__.py"],
    pathex=[ROOT],
    datas=[(ROOT + "/web", "web"), (ROOT + "/tizen", "tizen"), (ROOT + "/rsub/tv_ca", "rsub/tv_ca"),
           (ROOT + "/rsub/dub_worker.py", "rsub")],  # dublaj işçisi ayrı Python ortamında çalışır: dosya olarak
          # TV ile konuşma aracı (Tizen sdb, Apache-2.0); build.ps1 Tizen Studio'dan packaging/vendor/sdb'ye kopyalar
          + ([(ROOT + "/packaging/vendor/sdb/sdb.exe", "sdb")] if os.path.exists(ROOT + "/packaging/vendor/sdb/sdb.exe") else [])
          + collect_data_files("spellchecker"),  # İngilizce sözlük (en.json.gz); yoksa uygulama açılmıyordu
    hiddenimports=collect_submodules("winrt") + ["webview.platforms.edgechromium", "pystray._win32"],
    excludes=["pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="remote-subtitle",
          icon=ROOT + "/packaging/icon.ico", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="remote-subtitle", upx=False)
