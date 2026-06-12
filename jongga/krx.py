"""KRX 일자별 전종목 시세 — 과거 날짜의 '그날 돈이 몰린 종목'을 재구성한다

저장(collect)이 없던 과거 날짜도 조회할 수 있게 하는 원천.
KRX 정보데이터시스템의 공개 통계(전종목 시세, MDCSTAT01501)를 사용한다.
응답에는 종가·등락률·거래대금·시가총액이 전 종목분 들어 있어
유니버스(거래대금 상위 + 상승률 상위)를 그날 기준으로 그대로 다시 만들 수 있다.

KRX는 세션 쿠키 없이 바로 POST하면 빈 응답을 주는 경우가 있어,
한 세션으로 로더 페이지를 먼저 방문(쿠키 확보)한 뒤 데이터를 요청한다.
"""
import requests

DATA_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
WARMUP_URL = "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"
BLD = "dbms/MDC/STAT/standard/MDCSTAT01501"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": WARMUP_URL,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class KrxResult:
    """fetch_day 결과 — rows와 진단 정보(휴장/연결오류 구분용)"""
    def __init__(self, rows, status: str, detail: str = ""):
        self.rows = rows
        self.status = status          # ok / empty(휴장 추정) / error
        self.detail = detail


def _num(value) -> int:
    try:
        return int(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def _rate(value) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def parse_rows(out_block: list[dict]) -> list[dict]:
    """KRX OutBlock_1 → 유니버스 row 형식 (코스피·코스닥만)"""
    rows = []
    for r in out_block:
        market = (r.get("MKT_NM") or "").strip()
        if market not in ("KOSPI", "KOSDAQ"):
            continue
        code = (r.get("ISU_SRT_CD") or "").strip()
        if len(code) != 6:
            continue
        rows.append({
            "code": code,
            "name": (r.get("ISU_ABBRV") or "").strip(),
            "market": market,
            "price": _num(r.get("TDD_CLSPRC")),
            "change_rate": _rate(r.get("FLUC_RT")),
            "volume": _num(r.get("ACC_TRDVOL")),
            "trading_value": _num(r.get("ACC_TRDVAL")),       # 원
            "market_cap_eok": _num(r.get("MKTCAP")) // 100_000_000,
        })
    return rows


def fetch_day_detailed(date_yyyymmdd: str, timeout: int = 20) -> KrxResult:
    """해당 거래일의 전 종목 시세 + 진단. 세션 쿠키 확보 후 mktId ALL→개별 순으로 시도"""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(WARMUP_URL, timeout=timeout)   # JSESSIONID 쿠키 확보
    except requests.RequestException as exc:
        return KrxResult([], "error", f"KRX 접속 실패({exc.__class__.__name__})")

    def _request(mkt_id: str) -> tuple[list, str]:
        try:
            resp = session.post(DATA_URL, timeout=timeout, data={
                "bld": BLD, "locale": "ko_KR", "mktId": mkt_id,
                "trdDd": date_yyyymmdd, "share": "1", "money": "1",
                "csvxls_isNo": "false",
            })
        except requests.RequestException as exc:
            return [], f"요청 실패({exc.__class__.__name__})"
        if resp.status_code != 200:
            return [], f"HTTP {resp.status_code}"
        try:
            body = resp.json()
        except ValueError:
            return [], f"JSON 아님: {resp.text[:80]}"
        return body.get("OutBlock_1", []), ""

    block, err = _request("ALL")
    if not block:
        # ALL이 비거나 오류(HTTP 400 포함) → 코스피·코스닥 개별로 재시도
        merged, sub_err = [], ""
        for mkt in ("STK", "KSQ"):
            part, perr = _request(mkt)
            merged.extend(part)
            if perr and not sub_err:
                sub_err = perr
        block = merged
        if block:
            err = ""        # 개별 조회 성공 → 오류 초기화
        elif not err:
            err = sub_err   # ALL도 빈 응답 + 개별도 실패 → 개별 오류 사용

    rows = parse_rows(block)
    if rows:
        return KrxResult(rows, "ok")
    if err:
        return KrxResult([], "error", err)
    return KrxResult([], "empty", "응답은 받았으나 종목이 0개 (휴장일로 추정)")


def fetch_day(date_yyyymmdd: str, timeout: int = 20) -> list[dict]:
    """간편 버전 — rows만 반환 (실패·휴장 시 빈 리스트)"""
    return fetch_day_detailed(date_yyyymmdd, timeout).rows


def build_universe(rows: list[dict], cfg) -> list[dict]:
    """전 종목에서 '베토 2(거래대금)를 통과할 가능성이 있는' 종목을 전부 뽑는다 — 누락 0

    포함 조건 (베토 2와 수학적으로 동일):
      ① 거래대금 ≥ 중소형 최소 기준(기본 300억) — 중소형·테마주가 통과할 수 있는 최저선
      ② 거래대금 순위 ≤ 대형주 기준(기본 50위) — 대형주 판정 경로
    이 컷 아래 종목은 어떤 분류로도 베토 2를 통과할 수 없으므로 제외해도 결과가 같다.
    """
    floor = float(cfg("trading_value.midsmall_min_eok", 300)) * 1e8
    rank_max = int(cfg("trading_value.large_rank_max", 50))
    min_chg = float(cfg("universe.min_change_rate", 3.0))

    by_value = sorted((r for r in rows if r["trading_value"] > 0),
                      key=lambda r: r["trading_value"], reverse=True)
    out = []
    for rank, r in enumerate(by_value, start=1):
        if r["trading_value"] < floor and rank > rank_max:
            break  # 거래대금 내림차순이므로 이후는 전부 기준 미달
        src = []
        if rank <= rank_max:
            src.append("거래대금상위")
        if r["change_rate"] >= min_chg:
            src.append("상승률상위")
        out.append(dict(r, sources=",".join(src) or "거래대금 기준 통과"))
    return out
