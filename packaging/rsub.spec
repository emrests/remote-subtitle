# PyInstaller: python -m PyInstaller packaging/rsub.spec --noconfirm
from PyInstaller.utils.hooks import collect_submodules

ROOT = SPECPATH + "/.."

a = Analysis(
    [ROOT + "/rsub/__main__.py"],
    pathex=[ROOT],
    datas=[(ROOT + "/web", "web")],
    hiddenimports=collect_submodules("winrt") + ["webview.platforms.edgechromium", "pystray._win32"],
    excludes=["pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="remote-subtitle",
          icon=ROOT + "/packaging/icon.ico", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="remote-subtitle", upx=False)
