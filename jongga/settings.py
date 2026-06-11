"""설정 로딩 — 우선순위: 사용자 변경값(DB settings_override) > config/defaults.yaml

화면(M4)에서 바꾼 값은 DB에 저장되고, '기본값 복원'은 DB 저장값을 지우는 것이다.
defaults.yaml 원본은 절대 수정하지 않는다.
"""
import os
import sqlite3
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    # PyInstaller exe: 설정(.env)·데이터(data/)·config/는 exe 파일 옆에 둔다 (포터블)
    # 번들된 config 원본은 최초 실행 시 launcher가 exe 옆으로 복사한다
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "defaults.yaml"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jongga.sqlite3"
TOKEN_CACHE_PATH = DATA_DIR / "kis_token.json"

load_dotenv(BASE_DIR / ".env")

_OVERRIDE_DDL = "CREATE TABLE IF NOT EXISTS settings_override (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
_overrides_cache: dict | None = None


@lru_cache(maxsize=1)
def config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def yaml_default(path: str):
    """defaults.yaml의 원본 기본값 (없으면 None)"""
    node = config()
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def overrides() -> dict:
    global _overrides_cache
    if _overrides_cache is None:
        _overrides_cache = {}
        if DB_PATH.exists():
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(_OVERRIDE_DDL)
                    _overrides_cache = dict(conn.execute("SELECT key, value FROM settings_override"))
            except sqlite3.Error:
                pass
    return _overrides_cache


def _invalidate() -> None:
    global _overrides_cache
    _overrides_cache = None


def set_override(key: str, value) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_OVERRIDE_DDL)
        conn.execute(
            "INSERT INTO settings_override (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value), datetime.now().isoformat(timespec="seconds")),
        )
    _invalidate()


def remove_override(key: str) -> None:
    if not DB_PATH.exists():
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_OVERRIDE_DDL)
        conn.execute("DELETE FROM settings_override WHERE key = ?", (key,))
    _invalidate()


def clear_overrides() -> None:
    if not DB_PATH.exists():
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_OVERRIDE_DDL)
        conn.execute("DELETE FROM settings_override")
    _invalidate()


def _coerce(raw: str, reference):
    """저장된 문자열을 기본값의 타입에 맞춰 변환 (bool은 int의 하위 타입이라 먼저 검사)"""
    if isinstance(reference, bool):
        return str(raw).strip().lower() in ("1", "true", "on", "yes")
    try:
        if isinstance(reference, int):
            return int(float(raw))
        if isinstance(reference, float):
            return float(raw)
        if reference is None:
            f = float(raw)
            return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        pass
    return raw


def cfg(path: str, default=None):
    """점 표기로 설정값 조회. 예: cfg("kis.rate_limit_per_sec")"""
    ovr = overrides()
    base = yaml_default(path)
    if path in ovr:
        reference = base if base is not None else default
        return _coerce(ovr[path], reference)
    return base if base is not None else default


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require_kis_keys() -> tuple[str, str]:
    app_key = env("KIS_APP_KEY")
    app_secret = env("KIS_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError(
            "한국투자증권 API 키가 없습니다. "
            ".env.example을 복사해 .env 파일을 만들고 KIS_APP_KEY, KIS_APP_SECRET을 넣어주세요."
        )
    return app_key, app_secret


def kis_base_url() -> str:
    return env("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443").rstrip("/")
