"""KIS HTTP 클라이언트 — 호출 속도 제한 + 재시도 + 토큰 만료 자동 갱신"""
import time

import requests

from jongga.kis.auth import get_access_token
from jongga.settings import cfg, kis_base_url, require_kis_keys

TOKEN_EXPIRED_CODES = {"EGW00123", "EGW00121"}  # 토큰 만료/유효하지 않음


class KisApiError(RuntimeError):
    def __init__(self, msg_cd: str, msg: str):
        self.msg_cd = msg_cd
        super().__init__(f"[{msg_cd}] {msg}")


class KisClient:
    def __init__(self):
        self.base_url = kis_base_url()
        self.app_key, self.app_secret = require_kis_keys()
        self.session = requests.Session()
        self.timeout = cfg("kis.timeout_sec", 10)
        self.max_retries = cfg("kis.max_retries", 3)
        self._min_interval = 1.0 / float(cfg("kis.rate_limit_per_sec", 10))
        self._last_call = 0.0
        self._token = None

    def _throttle(self):
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _headers(self, tr_id: str) -> dict:
        if self._token is None:
            self._token = get_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def get(self, path: str, tr_id: str, params: dict) -> dict:
        last_error = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.get(
                    f"{self.base_url}{path}",
                    headers=self._headers(tr_id),
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2 ** attempt)
                continue

            try:
                body = resp.json()
            except ValueError:
                last_error = KisApiError(str(resp.status_code), resp.text[:200])
                time.sleep(2 ** attempt)
                continue

            msg_cd = str(body.get("msg_cd", ""))
            if msg_cd in TOKEN_EXPIRED_CODES:
                self._token = get_access_token(force=True)
                continue
            if resp.status_code == 200 and body.get("rt_cd") == "0":
                return body
            # 호출 한도 초과(500/EGW00201 등)는 잠시 쉬고 재시도
            last_error = KisApiError(msg_cd or str(resp.status_code), str(body.get("msg1", ""))[:200])
            time.sleep(2 ** attempt)

        raise last_error if last_error else KisApiError("UNKNOWN", "원인을 알 수 없는 오류")
