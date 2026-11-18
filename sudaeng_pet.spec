# -*- mode: python ; coding: utf-8 -*-


DROP_PATTERNS = [
    'opengl32sw',
    'd3dcompiler',
    'translations/',
    'qt6network',
    'qt6pdf',
    'qt6qml',
    'qt6quick',
    'qt6svg',
    'qt6opengl',
    'qt6virtualkeyboard',
    'imageformats/',
    'iconengines/',
    'generic/',
    'networkinformation/',
    'tls/',
    'platforminputcontexts/',
    'qminimal',
    'qoffscreen',
    'qdirect2d',
    'qtnetwork',
]


def keep(entry):
    name = entry[0].replace('\\', '/').lower()
    for pattern in DROP_PATTERNS:
        if pattern in name:
            return False
    return True


a = Analysis(
    ['sudaeng_pet.py'],
    pathex=[],
    binaries=[],
    datas=[('sudaeng_frames.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtNetwork',
        'tkinter',
        'unittest',
        'pydoc',
        'sqlite3',
        'asyncio',
        'multiprocessing',
        'xmlrpc',
    ],
    noarchive=False,
    optimize=0,
)

a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='sudaeng_pet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['sudaeng.ico'],
)
