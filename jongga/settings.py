"""설정 로딩 — 우선순위: 환경변수(.env) > DB 저장값(M4에서 추가) > config/defaults.yaml"""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "defaults.yaml"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jongga.sqlite3"
TOKEN_CACHE_PATH = DATA_DIR / "kis_token.json"

load_dotenv(BASE_DIR / ".env")


@lru_cache(maxsize=1)
def config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cfg(path: str, default=None):
    """점 표기로 설정값 조회. 예: cfg("kis.rate_limit_per_sec")"""
    node = config()
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require_kis_keys() -> tuple[str, str]:
    app_key = env("KIS_APP_KEY")
    app_secret = env("KIS_APP_SECRET")
    if not app_key or not app_secret:
        raise SystemExit(
            "한국투자증권 API 키가 없습니다.\n"
            ".env.example을 복사해 .env 파일을 만들고 KIS_APP_KEY, KIS_APP_SECRET을 넣어주세요."
        )
    return app_key, app_secret


def kis_base_url() -> str:
    return env("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443").rstrip("/")
