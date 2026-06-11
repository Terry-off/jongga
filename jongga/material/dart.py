"""DART 전자공시 클라이언트 — 공시 제목으로 재료·위험 이벤트를 찾는다

- 종목코드 → DART 고유번호(corp_code) 매핑은 corpCode.xml(zip)을 받아
  data/corp_code.json에 7일간 캐싱한다 (약 3,500개 상장사)
- 공시 목록: list.json (무료, 분당 1,000회 한도 — 충분)
"""
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta

import requests

from jongga.settings import DATA_DIR, env

BASE = "https://opendart.fss.or.kr/api"
CORP_CACHE = DATA_DIR / "corp_code.json"
CACHE_DAYS = 7


class DartError(RuntimeError):
    pass


def _api_key() -> str:
    key = env("DART_API_KEY")
    if not key:
        raise DartError("DART API 키가 없습니다 (.env의 DART_API_KEY)")
    return key


def parse_corp_zip(content: bytes) -> dict[str, str]:
    """corpCode.xml zip → {종목코드 6자리: corp_code} (상장사만)"""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    mapping = {}
    for el in ET.fromstring(xml_bytes).iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        corp = (el.findtext("corp_code") or "").strip()
        if len(stock) == 6 and corp:
            mapping[stock] = corp
    return mapping


def corp_map(force: bool = False) -> dict[str, str]:
    if not force and CORP_CACHE.exists():
        cached = json.loads(CORP_CACHE.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(cached.get("fetched_at", "1970-01-01"))
        if datetime.now() - fetched < timedelta(days=CACHE_DAYS):
            return cached["map"]
    resp = requests.get(f"{BASE}/corpCode.xml", params={"crtfc_key": _api_key()}, timeout=30)
    if resp.status_code != 200 or not resp.content[:2] == b"PK":  # zip 시그니처
        raise DartError(f"DART 고유번호 파일을 받지 못했습니다 (HTTP {resp.status_code})")
    mapping = parse_corp_zip(resp.content)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CORP_CACHE.write_text(
        json.dumps({"fetched_at": datetime.now().isoformat(), "map": mapping}, ensure_ascii=False),
        encoding="utf-8",
    )
    return mapping


def disclosures(corp_code: str, bgn_de: str, end_de: str) -> list[dict]:
    """기간 내 공시 목록. bgn_de/end_de: YYYYMMDD"""
    resp = requests.get(
        f"{BASE}/list.json",
        params={"crtfc_key": _api_key(), "corp_code": corp_code,
                "bgn_de": bgn_de, "end_de": end_de, "page_count": 100},
        timeout=10,
    )
    body = resp.json()
    status = body.get("status")
    if status == "013":  # 조회 결과 없음
        return []
    if status != "000":
        raise DartError(f"DART 오류 [{status}] {body.get('message', '')}")
    return [
        {
            "date": r.get("rcept_dt", ""),
            "title": (r.get("report_nm") or "").strip(),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r.get('rcept_no', '')}",
        }
        for r in body.get("list", [])
    ]
