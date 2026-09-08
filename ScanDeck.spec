# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("data", "data"),
    ("scandeck/locales", "scandeck/locales"),
]
binaries = []
hiddenimports = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.font",
    *collect_submodules("scandeck"),
]

pkg_datas, pkg_binaries, pkg_hidden = collect_all("openpyxl")
datas += pkg_datas
binaries += pkg_binaries
hiddenimports += pkg_hidden

a = Analysis(
    ["launch_scandeck.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScanDeck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ScanDeck",
)
