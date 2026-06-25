# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
pillow_datas, pillow_binaries, pillow_hiddenimports = collect_all("PIL")

hiddenimports = [
    "ollama",
    "openai",
    "anthropic",
    "google.generativeai",
    "google.ai.generativelanguage",
    "speech_recognition",
    "pyaudio",
    "PIL._tkinter_finder",
    *collect_submodules("setup"),
    *collect_submodules("ui"),
    *collect_submodules("voice_input"),
    *collect_submodules("speech_processor"),
    *ctk_hiddenimports,
    *pillow_hiddenimports,
]

a = Analysis(
    ["voice_input/main.py"],
    pathex=["."],
    binaries=ctk_binaries + pillow_binaries,
    datas=[
        ("setup/requirements.txt", "setup"),
        *ctk_datas,
        *pillow_datas,
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Phil",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Phil",
)
app = BUNDLE(
    coll,
    name="Phil.app",
    icon=None,
    bundle_identifier="com.phil.cadassistant",
)
