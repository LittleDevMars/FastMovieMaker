# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — FastMovieMaker
macOS: dist/FastMovieMaker.app
Windows/Linux: dist/FastMovieMaker/ (--onedir)
"""

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas, binaries, hiddenimports = [], [], []

for pkg in (
    "PySide6",
    "torch",
    "torchaudio",
    "faster_whisper",
    "ctranslate2",
    "imageio_ffmpeg",
    "edge_tts",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [
    ("resources", "resources"),
    ("src/ui/styles", "src/ui/styles"),
]

a = Analysis(
    ["main.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports + [
        "src.utils.resource_path",
        "difflib",
        "bisect",
    ],
    hookspath=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="FastMovieMaker",
    icon="resources/icon.ico",
    console=False,
    target_arch=None,
)

# macOS .app 번들
app = BUNDLE(
    exe,
    a.binaries,
    a.datas,
    name="FastMovieMaker.app",
    icon="resources/icon.png",
    bundle_identifier="com.fastmoviemaker.app",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": "0.4.1",
        "NSMicrophoneUsageDescription": "Whisper 음성 인식을 위해 마이크 접근이 필요합니다.",
    },
)

# Windows / Linux --onedir 배포판
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="FastMovieMaker",
)
