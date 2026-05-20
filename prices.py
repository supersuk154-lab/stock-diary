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
    # 자동매칭 실패 종목 수동 보정
    "KODEX 코리아소버린AI": "0115E0.KS",
    "알파벳 A": "GOOGL",
    "엔비디아": "NVDA",
    "SPDR PORTFOLIO S&P 500 GROWTH": "SPYG",
    "MARKETBETA RUSSELL 1000 GROWTH": "GGUS",
    "SCHWAB US LARGE CAP GROWTH": "SCHG",
    "JP MORGAN NASDAQ EQUITY PREMIUM": "JEPQ",
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


@st.cache_data(ttl=86400)
def _yahoo_search_ticker(stock_name: str) -> str | None:
    """야후파이낸스 Search API로 종목명 → 티커 조회 (하루 캐시)."""
    try:
        results = yf.Search(stock_name, max_results=3, news_count=0)
        for quote in results.quotes:
            symbol = quote.get("symbol", "")
            if symbol:
                return symbol
    except Exception:
        pass
    return None


def resolve_ticker(stock_name: str, ticker_hint: str = "", krx_map: dict | None = None) -> str | None:
    """종목명 → 야후파이낸스 티커 변환.

    1순위: TICKER_MAP (수동 보정, 빠름)
    2순위: KRX 전체 맵 (pykrx — 한국 상장 전 종목)
    3순위: 영문 1~7자 → 미국 티커 직접 시도 (SCHD, VOO, AAPL 등)
    4순위: 야후파이낸스 Search API (긴 영문 펀드명 등)
    5순위: ticker_hint (호출부에서 전달한 힌트)
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

    # 4. 야후파이낸스 Search API — 긴 영문 펀드명 등 자동 검색
    ticker = _yahoo_search_ticker(normalized)
    if ticker:
        return ticker

    # 5. 호출부 힌트
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

    def _parse(data) -> dict:
        prices = {}
        if data.empty:
            return prices
        close = data["Close"]
        is_df = hasattr(close, "columns")
        for ticker in tickers:
            try:
                series = (close[ticker] if is_df and ticker in close.columns
                          else (close if not is_df else None))
                if series is None:
                    prices[ticker] = None
                    continue
                series = series.dropna()
                val = float(series.iloc[-1]) if len(series) > 0 else None
                prices[ticker] = None if (val is None or math.isnan(val)) else val
            except Exception:
                prices[ticker] = None
        return prices

    try:
        # 1차 시도: 5분봉 (장중 실시간에 가깝게, 주말/휴장일에도 최근 데이터 포함)
        data = yf.download(
            list(tickers), period="1d", interval="5m",
            auto_adjust=True, progress=False
        )
        prices = _parse(data)
        # 유효 가격이 하나라도 있으면 반환
        if any(v is not None for v in prices.values()):
            return prices
    except Exception:
        prices = {}

    try:
        # 2차 폴백: 일봉 (주말·휴장일 종가 보장)
        data = yf.download(list(tickers), period="5d", auto_adjust=True, progress=False)
        return _parse(data)
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
        # 일봉 2일치: iloc[-2]=전일 종가, iloc[-1]=당일 현재가(장중 업데이트)
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
        # 주말/휴장일 대응을 위해 period="5d" 사용
        data = yf.download("KRW=X", period="5d", auto_adjust=True, progress=False)
        if data.empty:
            # [수정 #12] 마지막 성공 환율 캐시 사용
            return st.session_state.get("_last_usd_krw", _FALLBACK)
        _c = data["Close"].iloc[-1]
        val = float(_c.iloc[0] if hasattr(_c, "iloc") else _c)
        if math.isnan(val):
            return st.session_state.get("_last_usd_krw", _FALLBACK)
        # 성공한 환율을 세션에 캐싱
        st.session_state["_last_usd_krw"] = val
        return val
    except Exception:
        return st.session_state.get("_last_usd_krw", _FALLBACK)


def get_price_type(ticker: str) -> str:
    """티커와 현재 시각을 기준으로 실시간 시세인지 종가 시세인지를 판별합니다."""
    if not ticker:
        return "종가"
    
    # 한국 시간 기준
    now = datetime.datetime.now(KST)
    
    # 주말(토, 일)은 무조건 종가
    if now.weekday() >= 5:
        return "종가"
        
    h, m = now.hour, now.minute
    
    # 한국 주식 (.KS 또는 .KQ)
    if ticker.endswith(".KS") or ticker.endswith(".KQ"):
        # 9:00 ~ 15:30
        if (9, 0) <= (h, m) <= (15, 30):
            return "실시간"
        return "종가"
    else:
        # 미국 주식 (서머타임 고려하여 21:30 ~ 05:00)
        # 21:30 ~ 24:00 또는 00:00 ~ 05:00
        if (h >= 22 or (h == 21 and m >= 30)) or (h < 5):
            return "실시간"
        return "종가"

