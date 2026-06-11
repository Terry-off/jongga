"""접근 토큰 발급·캐싱

KIS 토큰은 24시간 유효하고 재발급이 1분에 1회로 제한되므로
파일 캐시(data/kis_token.json)를 반드시 거친다.
"""
import json
from datetime import datetime, timedelta

import requests

from jongga.settings import DATA_DIR, TOKEN_CACHE_PATH, kis_base_url, require_kis_keys

# 만료까지 이 시간 미만 남으면 미리 재발급
REFRESH_MARGIN = timedelta(minutes=10)


def _load_cached() -> str | None:
    try:
        cached = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(cached["expires_at"])
        if datetime.now() < expires_at - REFRESH_MARGIN:
            return cached["access_token"]
    except (FileNotFoundError, KeyError, ValueError):
        pass
    return None


def get_access_token(force: bool = False) -> str:
    if not force:
        token = _load_cached()
        if token:
            return token

    app_key, app_secret = require_kis_keys()
    try:
        resp = requests.post(
            f"{kis_base_url()}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            "한국투자증권 서버(openapi.koreainvestment.com:9443)에 연결할 수 없습니다. "
            "인터넷 연결과 방화벽/네트워크 정책(9443 포트 허용 여부)을 확인해주세요. "
            f"(상세: {exc.__class__.__name__})"
        ) from exc
    body = resp.json()
    if resp.status_code != 200 or "access_token" not in body:
        raise RuntimeError(
            "토큰 발급에 실패했습니다. .env의 앱키·시크릿이 실전투자용으로 올바른지 확인해주세요. "
            f"(응답: {body.get('error_code', resp.status_code)} {body.get('error_description', body)})"
        )

    expires_at = datetime.now() + timedelta(seconds=int(body.get("expires_in", 86400)))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(
        json.dumps({"access_token": body["access_token"], "expires_at": expires_at.isoformat()}),
        encoding="utf-8",
    )
    return body["access_token"]
