# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙 — 빌드: pyinstaller --noconfirm packaging/jongga.spec
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hiddenimports = collect_submodules("uvicorn") + ["anyio._backends._asyncio"]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "config"), "config"),
        (os.path.join(ROOT, "jongga", "web", "templates"), "jongga/web/templates"),
    ],
    hiddenimports=hiddenimports,
    # cryptography/pyOpenSSL은 사용하지 않음 — 제외해 용량 절감 (requests는 표준 ssl 사용)
    excludes=["tkinter", "unittest", "pytest", "cryptography", "OpenSSL"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="종가매매추천",
    console=True,          # 검은 창 유지 — 상태 메시지와 Ctrl+C 종료용
    upx=False,
    icon=None,
)
