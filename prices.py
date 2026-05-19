import math
import re
import datetime
import yfinance as yf
import streamlit as st
from app_constants import KST

# 국내 종목 중 pykrx가 이름을 다르게 반환하는 경우의 수동 보정 맵
# (pykrx 로딩 실패 시 최소 폴백 역할도 겸함)
TICKER_MAP = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "카카오": "035720.KS",
    "NAVER": "035420.KS",
    "KODEX 200": "069500.KS",
    "KODEX 코스닥 150": "229200.KS",
    "KODEX 코스닥150": "229200.KS",
    "KODEX 레버리지": "122630.KS",
    "KODEX 인버스": "114800.KS",
    "KODEX 미국S&P500TR": "379800.KS",
    "KODEX 미국나스닥100TR": "379810.KS",
    "KODEX TDF2040액티브 적격": "448730.KS",
    "KODEX TDF2040액티브": "448730.KS",
    "KODEX 삼성전자SK하이닉스채권혼합액티브": "486290.KS",
    "KODEX 삼성전자SK하이닉스채권혼합": "486290.KS",
    "TIGER 미국S&P500": "360750.KS",
    "TIGER 미국나스닥100": "133690.KS",
    "TIGER 코스피200": "102110.KS",
    "ARIRANG 미국S&P500": "269540.KS",
}


@st.cache_data(ttl=86400)
def _get_krx_name_map() -> dict:
    """KRX 전체 종목명 → 야후파이낸스 티커 맵 (pykrx 사용, 하루 캐시).
    KOSPI → xxxxxx.KS / KOSDAQ → xxxxxx.KQ 형식으로 변환."""
    try:
        from pykrx import stock as krx  # type: ignore
        today = datetime.datetime.now(KST).strftime("%Y%m%d")
        name_map: dict = {}
        for market, suffix in [("KOSPI", ".KS"), ("KOSDAQ", ".KQ")]:
            try:
                tickers = krx.get_market_ticker_list(today, market=market)
                for t in tickers:
                    name = krx.get_market_ticker_name(t)
                    if name and t:
                        name_map[name] = t + suffix
            except Exception:
                pass
        return name_map
    except Exception:
        return {}


def resolve_ticker(stock_name: str, ticker_hint: str = "", krx_map: dict | None = None) -> str | None:
    """종목명 → 야후파이낸스 티커 변환.

    1순위: TICKER_MAP (수동 보정, 빠름)
    2순위: KRX 전체 맵 (pykrx — 한국 상장 전 종목)
    3순위: 영문 1~6자 → 미국 티커 직접 시도 (SCHD, VOO, AAPL 등)
    4순위: ticker_hint (호출부에서 전달한 힌트)
    """
    normalized = " ".join(stock_name.split())

    # 1. 수동 보정 맵
    ticker = TICKER_MAP.get(normalized) or TICKER_MAP.get(stock_name)
    if ticker:
        return ticker

    # 2. KRX 전체 맵 (pykrx)
    _krx = krx_map if krx_map is not None else _get_krx_name_map()
    ticker = _krx.get(normalized) or _krx.get(stock_name)
    if ticker:
        return ticker

    # 3. 영문+숫자(점·하이픈 허용) 1~7자 → 미국 티커로 간주
    clean = normalized.strip()
    if re.match(r'^[A-Za-z][A-Za-z0-9\.\-]{0,6}$', clean):
        return clean.upper()

    # 4. 호출부 힌트
    if ticker_hint:
        return ticker_hint.strip() or None

    return None


def _market_time_bucket() -> str:
    """장중/장외 구분 캐시 버킷 — 장중은 15분, 장외는 1시간 단위로 변경."""
    now = datetime.datetime.now(KST)
    h, m = now.hour, now.minute
    kr_open = (9, 0) <= (h, m) < (15, 30)
    us_open = (h, m) >= (22, 30) or h < 5
    if kr_open or us_open:
        return f"{now.date()}-{h}-{(m // 15) * 15}"
    return f"{now.date()}-{h}"


@st.cache_data(ttl=3600)
def get_realtime_prices_bulk(tickers: tuple, time_bucket: str = "") -> dict:
    """tickers: 튜플로 전달 (list는 st.cache_data 해시 불가)
    time_bucket: 장중/장외 TTL 제어용 — _market_time_bucket() 결과 전달
    반환: {ticker: price} 딕셔너리"""
    if not tickers:
        return {}
    try:
        data = yf.download(list(tickers), period="1d", auto_adjust=True, progress=False)
        prices = {}
        if data.empty:
            return {}
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    val = float(data["Close"].iloc[-1])
                else:
                    val = float(data["Close"][ticker].iloc[-1])
                prices[ticker] = None if math.isnan(val) else val
            except Exception:
                prices[ticker] = None
        return prices
    except Exception:
        return {}


def get_realtime_price(ticker):
    """단일 티커 조회 — 내부적으로 bulk 함수 사용 (하위 호환용)."""
    result = get_realtime_prices_bulk((ticker,), time_bucket=_market_time_bucket())
    return result.get(ticker)


_MARKET_INDICES = {
    "KOSPI":   "^KS11",
    "KOSDAQ":  "^KQ11",
    "S&P 500": "^GSPC",
    "NASDAQ":  "^IXIC",
}

@st.cache_data(ttl=600)
def get_market_weather(time_bucket: str = "") -> dict:
    """4대 지수(KOSPI·KOSDAQ·S&P500·NASDAQ) 현재가 + 전일 대비 등락률.
    time_bucket: 캐시 무효화용 — _market_time_bucket() 결과 전달.
    반환: {지수명: {"current": float, "change_pct": float} | None}"""
    tickers = list(_MARKET_INDICES.values())
    result = {name: None for name in _MARKET_INDICES}
    try:
        data = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
        if data.empty:
            return result
        close = data["Close"]
        for name, ticker in _MARKET_INDICES.items():
            try:
                series = close[ticker] if len(tickers) > 1 else close
                series = series.dropna()
                if len(series) < 2:
                    continue
                prev, curr = float(series.iloc[-2]), float(series.iloc[-1])
                if math.isnan(prev) or math.isnan(curr) or prev == 0:
                    continue
                # pyrefly: ignore [unsupported-operation]
                result[name] = {"current": curr, "change_pct": (curr - prev) / prev * 100}
            except Exception:
                pass
    except Exception:
        pass
    return result


@st.cache_data(ttl=3600)
def get_usd_to_krw(time_bucket: str = "") -> float:
    """달러→원 환율 조회 (KRW=X 티커). 실패 시 마지막 성공 환율 또는 1,380원 기본값 반환."""
    _FALLBACK = 1380.0
    try:
        data = yf.download("KRW=X", period="1d", auto_adjust=True, progress=False)
        if data.empty:
            # [수정 #12] 마지막 성공 환율 캐시 사용
            return st.session_state.get("_last_usd_krw", _FALLBACK)
        val = float(data["Close"].iloc[-1])
        if math.isnan(val):
            return st.session_state.get("_last_usd_krw", _FALLBACK)
        # 성공한 환율을 세션에 캐싱
        st.session_state["_last_usd_krw"] = val
        return val
    except Exception:
        return st.session_state.get("_last_usd_krw", _FALLBACK)
