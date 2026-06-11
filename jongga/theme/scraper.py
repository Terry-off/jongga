"""네이버 금융 테마 수집 — 테마명 → 소속 종목 매핑 (DESIGN.md 4.6)

- 테마 목록 페이지(약 7쪽)에서 테마 상세 링크(no)를 모으고,
  각 상세 페이지에서 소속 종목코드를 긁는다.
- HTML 구조에 의존하므로 깨질 수 있다 → 파서를 fixture로 검증하고,
  실패 시 빈 결과를 돌려 '테마 확인 불가'(베토 아님)로 우아하게 후퇴한다.
- 무거운 작업(상세 250쪽)이므로 하루 1회 수집해 캐시에 저장하고,
  채점 단계(recommend)는 캐시만 읽는다.
"""
import html
import re
import sys
import time

import requests

BASE = "https://finance.naver.com"
LIST_URL = BASE + "/sise/theme.naver"
DETAIL_URL = BASE + "/sise/sise_group_detail.naver"
HEADERS = {"User-Agent": "Mozilla/5.0 (jongga theme collector)"}

# 테마 목록: sise_group_detail...type=theme&no=123 링크 + 테마명
_THEME_LINK = re.compile(
    r'href="[^"]*sise_group_detail\.naver\?type=theme&(?:amp;)?no=(\d+)"[^>]*>([^<]+)</a>'
)
# 테마 상세: 종목 링크 /item/main.naver?code=005930 + 종목명 (class="tltle"는 네이버 고유 오타 클래스)
_STOCK_LINK = re.compile(r'/item/main\.naver\?code=(\d{6})"[^>]*>([^<]+)</a>')


def parse_theme_list(page_html: str) -> list[tuple[str, str]]:
    """반환: [(theme_no, theme_name)] — 중복 제거, 순서 유지"""
    seen, out = set(), []
    for no, name in _THEME_LINK.findall(page_html):
        if no in seen:
            continue
        seen.add(no)
        out.append((no, html.unescape(name).strip()))
    return out


def parse_theme_detail(page_html: str) -> list[tuple[str, str]]:
    """반환: [(code, name)] — 테마 소속 종목, 중복 제거"""
    seen, out = set(), []
    for code, name in _STOCK_LINK.findall(page_html):
        if code in seen:
            continue
        seen.add(code)
        out.append((code, html.unescape(name).strip()))
    return out


def _get(url: str, params: dict, timeout: int) -> str | None:
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return None
        resp.encoding = resp.apparent_encoding or "euc-kr"
        return resp.text
    except requests.RequestException:
        return None


def collect(max_pages: int = 10, delay: float = 0.4, timeout: int = 10,
            progress=lambda *_: None) -> dict[str, list[str]]:
    """테마명 → [종목코드]. 실패 시 빈 dict (호출측에서 '확인 불가' 처리)"""
    themes: list[tuple[str, str]] = []
    for page in range(1, max_pages + 1):
        page_html = _get(LIST_URL, {"page": page}, timeout)
        if not page_html:
            break
        found = parse_theme_list(page_html)
        if not found:
            break
        themes.extend(found)
        # 다음 페이지가 없으면(테마가 더 안 나오면) 중단
        if len(found) < 5:
            break
        time.sleep(delay)

    # no 기준 중복 제거
    uniq = {}
    for no, name in themes:
        uniq.setdefault(no, name)

    result: dict[str, list[str]] = {}
    total = len(uniq)
    for i, (no, name) in enumerate(uniq.items(), start=1):
        detail = _get(DETAIL_URL, {"type": "theme", "no": no}, timeout)
        if detail:
            members = [code for code, _ in parse_theme_detail(detail)]
            if members:
                result[name] = members
        progress(i, total, name)
        time.sleep(delay)

    if not result:
        print("(안내) 네이버 테마 수집 결과가 비었습니다 — 테마 항목은 '확인 불가'로 처리됩니다.",
              file=sys.stderr)
    return result
