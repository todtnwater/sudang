# -*- mode: python ; coding: utf-8 -*-


DROP_PATTERNS = [
    'translations/',
    'qtnetwork',
    'qtpdf',
    'qtqml',
    'qtquick',
    'qtvirtualkeyboard',
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
    hiddenimports=['Quartz'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtNetwork',
        'tkinter',
        'unittest',
        'pydoc',
        'sqlite3',
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
    [],
    exclude_binaries=True,
    name='sudaeng_pet',
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
    name='sudaeng_pet',
)

app = BUNDLE(
    coll,
    name='sudaeng_pet.app',
    icon='sudaeng.ico',
    bundle_identifier='com.todtnwater.sudaengpet',
    info_plist={
        'CFBundleName': 'sudaeng_pet',
        'CFBundleDisplayName': '수댕이',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
    },
)
