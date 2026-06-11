"""KIS 도메인 API — TR ID·파라미터를 한곳에 모아 문서 변경 시 여기만 고친다

수치 필드는 문자열로 오므로 전부 int/float로 정규화해서 반환한다.
거래대금(acml_tr_pbmn) 단위는 원, 시가총액(hts_avls) 단위는 억 원.
"""
from jongga.kis.client import KisClient


def _i(value, default=0) -> int:
    try:
        return int(str(value).replace(",", "") or default)
    except (TypeError, ValueError):
        return default


def _f(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", "") or default)
    except (TypeError, ValueError):
        return default


def volume_rank(client: KisClient, market: str = "0000", sort: str = "3") -> list[dict]:
    """거래량/거래대금 순위 (실전 전용, 1회 최대 30종목)

    market: 0000 전체 / 0001 코스피 / 1001 코스닥
    sort(FID_BLNG_CLS_CODE): 0 평균거래량 / 1 거래증가율 / 2 회전율 / 3 거래금액순
    """
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/volume-rank",
        tr_id="FHPST01710000",
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": market,
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": sort,
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "0000000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
        },
    )
    return [
        {
            "rank": _i(row.get("data_rank")),
            "code": row.get("mksc_shrn_iscd", ""),
            "name": row.get("hts_kor_isnm", ""),
            "price": _i(row.get("stck_prpr")),
            "change_rate": _f(row.get("prdy_ctrt")),
            "volume": _i(row.get("acml_vol")),
            "trading_value": _i(row.get("acml_tr_pbmn")),
        }
        for row in body.get("output", [])
    ]


def fluctuation_rank(client: KisClient, market: str = "0000") -> list[dict]:
    """등락률 순위 — 상승률 상위 (실전 전용)"""
    body = client.get(
        "/uapi/domestic-stock/v1/ranking/fluctuation",
        tr_id="FHPST01700000",
        params={
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20170",
            "fid_input_iscd": market,
            "fid_rank_sort_cls_code": "0",  # 0: 상승률순
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "1",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": "",
            "fid_rsfl_rate2": "",
        },
    )
    return [
        {
            "rank": _i(row.get("data_rank")),
            "code": row.get("stck_shrn_iscd", ""),
            "name": row.get("hts_kor_isnm", ""),
            "price": _i(row.get("stck_prpr")),
            "change_rate": _f(row.get("prdy_ctrt")),
            "volume": _i(row.get("acml_vol")),
        }
        for row in body.get("output", [])
    ]


def current_price(client: KisClient, code: str) -> dict:
    """현재가 + 종목 상태 플래그 (경보·과열·정리매매 등은 베토 6에서 사용)"""
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        tr_id="FHKST01010100",
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
    )
    out = body.get("output", {})
    return {
        "code": code,
        "price": _i(out.get("stck_prpr")),
        "change_rate": _f(out.get("prdy_ctrt")),
        "open": _i(out.get("stck_oprc")),
        "high": _i(out.get("stck_hgpr")),
        "low": _i(out.get("stck_lwpr")),
        "volume": _i(out.get("acml_vol")),
        "trading_value": _i(out.get("acml_tr_pbmn")),
        "market_cap_eok": _i(out.get("hts_avls")),
        "market": out.get("rprs_mrkt_kor_name", ""),
        "sector_name": out.get("bstp_kor_isnm", ""),
        "w52_high": _i(out.get("w52_hgpr")),
        # 종목 상태 플래그 — 51 관리 / 52 투자위험 / 53 투자경고 / 54 투자주의 / 58 거래정지 등
        "status_code": out.get("iscd_stat_cls_code", ""),
        "market_warn_code": out.get("mrkt_warn_cls_code", ""),  # 00 없음 / 01 주의 / 02 경고 / 03 위험
        "caution_yn": out.get("invt_caful_yn", ""),
        "short_overheat_yn": out.get("short_over_yn", ""),
        "halt_yn": out.get("temp_stop_yn", ""),
        "delisting_yn": out.get("sltr_yn", ""),
    }


def daily_candles(client: KisClient, code: str, start: str, end: str) -> list[dict]:
    """일봉 (수정주가 적용, 1회 최대 100건). start/end: YYYYMMDD"""
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        tr_id="FHKST03010100",
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start,
            "FID_INPUT_DATE_2": end,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",  # 0: 수정주가
        },
    )
    candles = [
        {
            "date": row.get("stck_bsop_date", ""),
            "open": _i(row.get("stck_oprc")),
            "high": _i(row.get("stck_hgpr")),
            "low": _i(row.get("stck_lwpr")),
            "close": _i(row.get("stck_clpr")),
            "volume": _i(row.get("acml_vol")),
            "trading_value": _i(row.get("acml_tr_pbmn")),
        }
        for row in body.get("output2", [])
        if row.get("stck_bsop_date")
    ]
    candles.sort(key=lambda c: c["date"])
    return candles


def _prev_minute(hhmmss: str) -> str:
    total = int(hhmmss[:2]) * 60 + int(hhmmss[2:4]) - 1
    return f"{total // 60:02d}{total % 60:02d}00"


def minute_candles(client: KisClient, code: str, start_hhmm: str = "0900") -> list[dict]:
    """당일 분봉 — 1회 30건이라 15:30부터 뒤로 페이지를 넘기며 모은다"""
    rows: dict[str, dict] = {}
    hour = "153000"
    for _ in range(16):
        body = client.get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id="FHKST03010200",
            params={
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": hour,
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )
        got = [r for r in body.get("output2", []) if r.get("stck_cntg_hour")]
        if not got:
            break
        for r in got:
            t = r["stck_cntg_hour"][:4]
            rows[t] = {
                "time": t,
                "open": _i(r.get("stck_oprc")),
                "high": _i(r.get("stck_hgpr")),
                "low": _i(r.get("stck_lwpr")),
                "close": _i(r.get("stck_prpr")),
                "volume": _i(r.get("cntg_vol")),
            }
        earliest = min(r["stck_cntg_hour"] for r in got)
        if earliest[:4] <= start_hhmm:
            break
        hour = _prev_minute(earliest)
    return sorted((r for r in rows.values() if r["time"] >= start_hhmm), key=lambda r: r["time"])


def investor_trend(client: KisClient, code: str) -> list[dict]:
    """종목별 일별 수급(외국인·기관·개인 순매수량) — 당일분은 장중 미확정일 수 있다"""
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        tr_id="FHKST01010900",
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
    )
    rows = [
        {
            "date": r.get("stck_bsop_date", ""),
            "person_net": _i(r.get("prsn_ntby_qty")),
            "foreign_net": _i(r.get("frgn_ntby_qty")),
            "inst_net": _i(r.get("orgn_ntby_qty")),
        }
        for r in body.get("output", [])
        if r.get("stck_bsop_date")
    ]
    rows.sort(key=lambda r: r["date"])
    return rows


def index_price(client: KisClient, code: str = "0001") -> dict:
    """업종/지수 현재가. code: 0001 코스피 / 1001 코스닥"""
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-index-price",
        tr_id="FHPUP02100000",
        params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": code},
    )
    out = body.get("output", {})
    last = _f(out.get("bstp_nmix_prpr"))
    return {
        "code": code,
        "price": last,
        "change": _f(out.get("bstp_nmix_prdy_vrss")),
        "change_rate": _f(out.get("bstp_nmix_prdy_ctrt")),
        "prev_close": last - _f(out.get("bstp_nmix_prdy_vrss")),
    }


def index_minutes(client: KisClient, code: str = "0001") -> list[dict]:
    """업종/지수 분봉 — 응답 필드가 문서 버전에 따라 달라 보수적으로 매핑한다"""
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice",
        tr_id="FHKUP03500200",
        params={
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_HOUR_1": "60",  # 60초 = 1분봉
            "FID_PW_DATA_INCU_YN": "Y",
            "FID_ETC_CLS_CODE": "0",
        },
    )
    rows = []
    for r in body.get("output2", []):
        t = (r.get("stck_cntg_hour") or r.get("bsop_hour") or "")[:4]
        price = _f(r.get("bstp_nmix_prpr") or r.get("optn_prpr") or r.get("stck_prpr"))
        if t and price:
            rows.append({"time": t, "price": price})
    rows.sort(key=lambda r: r["time"])
    out, prev = [], rows[0]["price"] if rows else 0.0
    for r in rows:
        out.append({"time": r["time"], "open": prev, "high": max(prev, r["price"]),
                    "low": min(prev, r["price"]), "close": r["price"], "volume": 0})
        prev = r["price"]
    return out
