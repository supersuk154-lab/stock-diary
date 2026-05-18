import math
import datetime
from datetime import timezone, timedelta
import yfinance as yf
import streamlit as st

KST = timezone(timedelta(hours=9))

TICKER_MAP = {
    # 개별 주식
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "카카오": "035720.KS",
    "NAVER": "035420.KS",
    "Alphabet": "GOOGL",
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "NVIDIA": "NVDA",
    "Tesla": "TSLA",
    # KODEX ETF
    "KODEX 200": "069500.KS",
    "KODEX 코스닥 150": "229200.KS",
    "KODEX 코스닥150": "229200.KS",
    "KODEX 레버리지": "122630.KS",
    "KODEX 인버스": "114800.KS",
    "KODEX 미국S&P500TR": "379800.KS",
    "KODEX 미국나스닥100TR": "379810.KS",
    "KODEX TDF2040액티브 적격": "448730.KS",
    # "KODEX 코리아소버린AI" — yfinance 미등록 신규 ETF, 추후 확인 후 추가
    "KODEX 삼성전자SK하이닉스채권혼합액티브": "486290.KS",
    # TIGER ETF
    "TIGER 미국S&P500": "360750.KS",
    "TIGER 미국나스닥100": "133690.KS",
    "TIGER 코스피200": "102110.KS",
    # ARIRANG ETF
    "ARIRANG 미국S&P500": "269540.KS",
}


def _market_time_bucket() -> str:
    """장중/장외 구분 캐시 버킷 — 장중은 15분, 장외는 1시간 단위로 변경."""
    now = datetime.datetime.now(KST)
    h, m = now.hour, now.minute
    kr_open = (9, 0) <= (h, m) < (15, 30)    # 한국장: 9:00~15:30 KST
    us_open = (h, m) >= (22, 30) or h < 5    # 미국장: 22:30~05:00 KST
    if kr_open or us_open:
        return f"{now.date()}-{h}-{(m // 15) * 15}"  # 15분 단위
    return f"{now.date()}-{h}"               # 장외: 1시간 단위


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


@st.cache_data(ttl=3600)
def get_usd_to_krw(time_bucket: str = "") -> float:
    """달러→원 환율 조회 (KRW=X 티커). 실패 시 1,380원 기본값 반환."""
    try:
        data = yf.download("KRW=X", period="1d", auto_adjust=True, progress=False)
        if data.empty:
            return 1380.0
        val = float(data["Close"].iloc[-1])
        return val if not math.isnan(val) else 1380.0
    except Exception:
        return 1380.0
