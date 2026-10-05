# -*- mode: python ; coding: utf-8 -*-

# curl_cffi is imported lazily and by name inside app/pipeline/fetcher.py, so PyInstaller's
# static analysis never sees it and would leave it out of the build entirely.
#
# collect_submodules is what actually does the work: it pulls all 18 modules including the
# compiled _wrapper.pyd, and in curl_cffi 0.9.0 libcurl is statically linked into that, so
# no separate DLL is needed. collect_dynamic_libs returns nothing today -- it is kept
# because a later version, or another platform, may ship libcurl as its own file, and a
# silently missing DLL is the expensive failure here.
#
# Expensive because it is silent: the fetch ladder catches the ImportError and drops two
# rungs, so the packaged app would simply go back to failing on every 403 site while every
# test still passed. Verified by building and RUNNING a frozen probe: inside the exe, plain
# requests got HTTP 403 from startup.jobs and curl_cffi got 200 with 433,228 bytes.
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=collect_dynamic_libs('curl_cffi'),
    datas=[('Icon.ico', '.')],
    hiddenimports=(collect_submodules('curl_cffi')
                    # lingua is a compiled Rust extension with the language models built
                    # into the .pyd, and trafilatura reaches several of its own submodules
                    # by name. Both are silent failures if left out: language detection
                    # would raise on the first listing, and description extraction would
                    # quietly fall back to the noisier route inside the exe only.
                    + collect_submodules('lingua')
                    # rapidfuzz is a compiled C++ extension whose scorers live in
                    # per-scorer .pyd modules loaded by name -- dedup is the only caller,
                    # and without these the Filter button raises on its second step.
                    + collect_submodules('rapidfuzz')
                    + collect_submodules('trafilatura')
                    # The Entry, Mid and Senior profiles are loaded by name
                    # (importlib.import_module in app/pipeline/profiles/__init__.py), which
                    # static analysis cannot follow. Left out, choosing any of those Levels
                    # would raise inside the exe only, while every test passed.
                    + collect_submodules('app.pipeline.profiles')
                    # The résumé readers are imported inside the functions that use them.
                    + collect_submodules('pypdf')
                    + collect_submodules('docx')),
    hookspath=[],
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
    a.binaries,
    a.datas,
    [],
    name='RoleHound',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Icon.ico'],
)
