# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH)

datas = [
    ('models/asr', 'models/asr'),
    ('models/punctuation', 'models/punctuation'),
    ('config.toml', '.'),
]
binaries = []
hiddenimports = []
if sys.platform != 'win32':
    backend = 'darwin' if sys.platform == 'darwin' else 'xorg'
    hiddenimports += [f'pynput.{part}._{backend}' for part in ('keyboard', 'mouse', '_util')]
tmp_ret = collect_all('sherpa_onnx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['packaging/pyinstaller-hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoxPill',
    icon=str(project_root / 'assets' / 'voxpill.ico'),
    version=str(project_root / 'packaging' / 'version_info.txt') if sys.platform == 'win32' else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.' if sys.platform == 'win32' else '_internal',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VoxPill',
)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='VoxPill.app',
        icon=str(project_root / 'assets' / 'voxpill.icns'),
        bundle_identifier='io.github.gaivrt.voxpill',
        info_plist={
            'CFBundleShortVersionString': '1.2.1',
            'NSMicrophoneUsageDescription': 'VoxPill transcribes your voice locally while you hold the recording hotkey.',
            'LSUIElement': True,
        },
    )
