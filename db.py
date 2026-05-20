import datetime
import logging
import streamlit as st
from app_constants import KST

__all__ = [
    "KST",
    "to_kst_str",
    "calculate_scores",
    "calculate_investment_score",
    "has_tag",
    "get_past_context",
    "get_recent_journals",
    "get_real_inventory",
    "get_dividend_total",
    "delete_journal",
]



def to_kst_str(iso_ts: str) -> str:
    """Postgres timestamptz → 'YYYY-MM-DD HH:MM:SS' (KST)"""
    if not iso_ts:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_ts


def calculate_scores(supabase, user_id: str = ""):
    """최근 30일 일기를 기반으로 투자 능력치 점수를 계산."""
    if not user_id:
        return {"원칙 준수": 0, "멘탈 방어": 0, "성실도": 0, "자기 객관화": 0}

    thirty_days_ago = (
        datetime.datetime.now(timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()

    try:
        response = (
            supabase.table("journals")
            .select("created_at, tags")
            .eq("user_id", user_id)
            .gte("created_at", thirty_days_ago)
            .order("created_at", desc=True)
            .execute()
        )
        rows = response.data
    except Exception as e:
        # [수정 #10] UI 호출 대신 logging 사용 — 데이터 레이어에서 관심사 분리
        logging.warning(f"점수 조회 실패: {e}")
        rows = []

    tags_list = [r["tags"] for r in rows if r.get("tags")]
    dates = sorted(
        list(set([to_kst_str(r["created_at"]).split()[0] for r in rows if r.get("created_at")])),
        reverse=True
    )

    routine_count = sum(1 for t in tags_list if "#월급날정기매수" in t)
    dividend_count = sum(1 for t in tags_list if "#배당금달달해" in t)
    principle = min((routine_count * 70) + (dividend_count * 30), 100)

    panic_count = sum(1 for t in tags_list if "#뇌동매매반성" in t)
    mental = max(100 - (panic_count * 30), 0)

    review_count = sum(1 for t in tags_list if "#오늘의실수" in t)
    review = min(review_count * 25, 100)

    streak = 0
    today = datetime.datetime.now(KST).date()
    yesterday = today - datetime.timedelta(days=1)

    if dates:
        first_record_date = datetime.datetime.strptime(dates[0], "%Y-%m-%d").date()
        if first_record_date == today or first_record_date == yesterday:
            current_check_date = first_record_date
            for d_str in dates:
                d = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                if d == current_check_date:
                    streak += 1
                    current_check_date -= datetime.timedelta(days=1)
                else:
                    break

    consistency = min(streak * 3.3, 100)
    return {"원칙 준수": principle, "멘탈 방어": mental, "성실도": consistency, "자기 객관화": review}


def calculate_investment_score(supabase, user_id: str) -> dict:
    """
    실제 보유 종목 + 거래 이력 + 일기 태그를 종합해 100점 만점 투자 점수를 계산.
    반환 구조:
      {
        "total": int,
        "grade": str, "grade_emoji": str,
        "categories": {
            "종목 품질": {"score": int, "max": 40},
            "장기 보유": {"score": int, "max": 35},
            "투자 습관": {"score": int, "max": 25},
        },
        "stock_evals": [{"name", "ticker", "type", "quality_pts", "hold_days", "hold_pts"}, ...],
        "habit_detail": {"routine": int, "defense": int, "panic": int},
      }
    """
    import re as _re

    # ── 우량주 / ETF 분류 기준 ──────────────────────────
    US_ETFS = {
        "VOO","QQQ","SPY","SCHD","JEPI","VTI","IVV","VYM","QYLD","JEPQ",
        "DIVO","DGRO","NOBL","SPHD","HDV","DVY","VIG","SDY","SPLG","CSPX",
        "GLD","SLV","BND","AGG","TLT","IAU","ARKK","XLK","XLE","XLF",
    }
    US_BLUE_CHIPS = {
        "AAPL","MSFT","NVDA","GOOGL","GOOG","AMZN","META","TSLA","BRK-B",
        "JPM","JNJ","UNH","V","MA","PG","HD","COST","ABBV","LLY","WMT",
        "BAC","XOM","CVX","MCD","KO","PEP","MRK","TMO","NEE",
    }
    KR_ETF_KEYWORDS = ["KODEX","TIGER","ACE","KINDEX","HANARO","ARIRANG","KOSEF","SMART","FOCUS"]
    KR_BLUE_CHIPS = {
        "005930.KS","000660.KS","035420.KS","005380.KS","051910.KS",
        "035720.KS","207940.KS","006400.KS","373220.KS","068270.KS",
        "003550.KS","015760.KS","030200.KS","032830.KS","086790.KS",
    }

    # ── 1. 보유 종목 ────────────────────────────────────
    inventory = get_real_inventory(user_id, supabase)

    # ── 2. 종목별 최초 매수일 ────────────────────────────
    try:
        trades_resp = (
            supabase.table("trades")
            .select("stock_name, created_at, quantity")
            .eq("user_id", user_id)
            .gt("quantity", 0)
            .order("created_at", desc=False)
            .execute()
        )
        trades_data = trades_resp.data or []
    except Exception:
        trades_data = []

    first_buy_map = {}
    for t in trades_data:
        sn = t.get("stock_name", "")
        if sn and sn not in first_buy_map:
            try:
                dt = datetime.datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
                first_buy_map[sn] = dt
            except Exception:
                pass

    # ── 3. 최근 30일 일기 태그 ──────────────────────────
    thirty_ago = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()
    try:
        j_resp = (
            supabase.table("journals")
            .select("tags")
            .eq("user_id", user_id)
            .gte("created_at", thirty_ago)
            .execute()
        )
        tags_list = [r["tags"] for r in (j_resp.data or []) if r.get("tags")]
    except Exception:
        tags_list = []

    now = datetime.datetime.now(datetime.timezone.utc)

    # ── 카테고리 1: 종목 품질 (40점) ────────────────────
    stock_evals = []
    raw_quality = 0

    for item in inventory:
        name = item.get("종목", "")
        ticker = (item.get("ticker") or "").strip().upper()

        is_kr_etf = any(kw in name for kw in KR_ETF_KEYWORDS)
        is_us_etf = ticker in US_ETFS
        is_kr_blue = ticker in KR_BLUE_CHIPS
        is_us_blue = ticker in US_BLUE_CHIPS

        if is_kr_etf or is_us_etf:
            stype, qpts = "ETF (분산투자)", 8
        elif is_kr_blue or is_us_blue:
            stype, qpts = "우량주", 6
        elif ticker.endswith(".KS") or ticker.endswith(".KQ"):
            stype, qpts = "한국 주식", 4
        elif _re.match(r"^[A-Z]{1,5}(-[A-Z])?$", ticker):
            stype, qpts = "미국 주식", 4
        else:
            stype, qpts = "미분류", 2

        stock_evals.append({
            "name": name, "ticker": ticker or "—",
            "type": stype, "quality_pts": qpts,
            "hold_days": 0, "hold_pts": 0,
        })
        raw_quality += qpts

    quality_score = min(raw_quality, 40)

    # ── 카테고리 2: 장기 보유 (35점) ────────────────────
    raw_hold = 0
    for ev in stock_evals:
        first_buy = first_buy_map.get(ev["name"])
        hold_days = (now - first_buy).days if first_buy else 0
        ev["hold_days"] = hold_days

        if hold_days >= 365:
            hpts = 10
        elif hold_days >= 180:
            hpts = 8
        elif hold_days >= 90:
            hpts = 6
        elif hold_days >= 30:
            hpts = 3
        else:
            hpts = 1
        ev["hold_pts"] = hpts
        raw_hold += hpts

    hold_score = min(raw_hold, 35)

    # ── 카테고리 3: 투자 습관 (25점) ────────────────────
    routine_cnt = sum(1 for t in tags_list if "#월급날정기매수" in t)
    defense_cnt = sum(
        1 for t in tags_list
        if any(k in t for k in ["#존버는승리한다", "#오늘은안봤다", "#한템포쉬어가기", "#배당금달달해"])
    )
    panic_cnt = sum(1 for t in tags_list if "#뇌동매매반성" in t)

    raw_habit = (routine_cnt * 5) + (defense_cnt * 3) - (panic_cnt * 5)
    habit_score = max(0, min(raw_habit, 25))

    total = quality_score + hold_score + habit_score

    # ── 등급 ────────────────────────────────────────────
    if total >= 90:
        grade, grade_emoji = "전설의 투자자", "🏆"
    elif total >= 75:
        grade, grade_emoji = "장기투자 고수", "💎"
    elif total >= 60:
        grade, grade_emoji = "성장하는 투자자", "📈"
    elif total >= 45:
        grade, grade_emoji = "기초 다지는 중", "🌱"
    else:
        grade, grade_emoji = "투자 입문 단계", "🐣"

    return {
        "total": total,
        "grade": grade,
        "grade_emoji": grade_emoji,
        "categories": {
            "종목 품질": {"score": quality_score, "max": 40},
            "장기 보유": {"score": hold_score, "max": 35},
            "투자 습관": {"score": habit_score, "max": 25},
        },
        "stock_evals": stock_evals,
        "habit_detail": {
            "routine": routine_cnt,
            "defense": defense_cnt,
            "panic": panic_cnt,
        },
    }


def has_tag(tags: list, keyword: str) -> bool:
    """선택된 태그 목록에 특정 키워드가 포함되어 있는지 확인."""
    if not tags:
        return False
    return any(keyword in t for t in tags)


@st.cache_data(ttl=60)
def get_past_context(tags, _supabase, user_id: str = ""):
    """현재 선택된 태그 중 가장 중요한 감정 태그를 찾아 과거 일기를 소환."""
    if not user_id:
        return ""
    if not tags:
        return ""

    priority_keywords = ["#뇌동매매반성", "#오늘좀흔들", "#오늘의실수"]
    core_tag = None

    for t in tags:
        if any(keyword in t for keyword in priority_keywords):
            core_tag = t
            break

    if not core_tag:
        core_tag = tags[0]

    try:
        response = (
            _supabase.table("journals")
            .select("created_at, content")
            .eq("user_id", user_id)
            .like("tags", f"%{core_tag}%")
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
        rows = response.data
    except Exception:
        rows = []

    if not rows:
        return ""

    context = f"\n\n[참고 데이터: 사용자의 과거 '{core_tag}' 관련 기록]\n"
    for r in rows:
        date_str = to_kst_str(r["created_at"]).split()[0]
        context += f"- {date_str}: {r['content']}\n"
    return context


# [수정 #11] TTL 10→120초로 증가 (저장 직후 .clear() 호출 패턴이 이미 있으므로 안전)
@st.cache_data(ttl=120)
def get_recent_journals(user_id: str, _supabase, limit: int = 50):
    """user_id를 캐시 키에 포함해서 사용자별로 분리된 캐시를 사용."""
    try:
        response = (
            _supabase.table("journals")
            .select("id, created_at, tags, content, ai_feedback")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    except Exception as e:
        st.error(f"일기 조회 실패: {e}")
        return []


@st.cache_data(ttl=30)
def get_real_inventory(user_id: str, _supabase):
    """trades 테이블에서 매수/매도 내역을 가져와 종목별 총 수량과 평단가를 정확히 계산합니다."""
    try:
        response = (
            _supabase.table("trades")
            .select("stock_name, quantity, price, currency, type, ticker")
            .eq("user_id", user_id)
            .neq("type", "dividend")
            .execute()
        )
        trades = response.data

        if not trades:
            return []

        inventory_map = {}
        for t in trades:
            name = t.get("stock_name")
            raw_qty = float(t.get("quantity", 0))
            price = float(t.get("price", 0))
            currency = t.get("currency", "KRW")
            trade_type = t.get("type", "buy")
            ticker = t.get("ticker")

            if not name or raw_qty == 0:
                continue

            qty = -abs(raw_qty) if trade_type == "sell" else abs(raw_qty)

            # 종목명 정규화 (앞뒤 및 다중 공백 정리)
            normalized_name = " ".join(name.split())
            
            # 티커가 존재하면 티커를 대표 키로 삼아 병합, 없으면 정규화된 종목명을 대표 키로 삼음
            group_key = ticker if ticker else normalized_name

            if group_key not in inventory_map:
                inventory_map[group_key] = {
                    "현재수량": 0,
                    "총매수수량": 0,
                    "총매수금액": 0,
                    "통화": currency,
                    "ticker": ticker,
                    "종목": name,  # 대표 종목명
                }

            # 기존 레코드에 ticker가 없고 새 레코드에 있으면 업데이트
            if not inventory_map[group_key]["ticker"] and ticker:
                inventory_map[group_key]["ticker"] = ticker

            if qty > 0:
                inventory_map[group_key]["총매수수량"] += qty
                inventory_map[group_key]["총매수금액"] += (qty * price)

            inventory_map[group_key]["현재수량"] += qty

        result = []
        for group_key, data in inventory_map.items():
            if data["현재수량"] > 0:
                avg_price = data["총매수금액"] / data["총매수수량"] if data["총매수수량"] > 0 else 0
                result.append({
                    "종목": data["종목"],
                    "수량": data["현재수량"],
                    "평단가": avg_price,
                    "통화": data["통화"],
                    "ticker": data["ticker"],
                })
        return result
    except Exception as e:
        st.error(f"재고 데이터 집계 실패: {e}")
        return []


def delete_journal(journal_id: str, user_id: str, supabase) -> None:
    """일기를 삭제합니다. user_id를 함께 검증해 타인의 일기는 절대 삭제하지 않습니다."""
    if not journal_id or not user_id:
        raise ValueError("journal_id와 user_id는 필수입니다.")
    supabase.table("journals").delete().eq("id", journal_id).eq("user_id", user_id).execute()
    # 캐시 무효화
    get_recent_journals.clear()


@st.cache_data(ttl=30)
def get_dividend_total(user_id: str, _supabase) -> dict:
    """배당금 합계 조회. 과거 데이터(quantity)와 신규 데이터(dividend_amount) 모두 호환."""
    try:
        response = (
            _supabase.table("trades")
            .select("quantity, dividend_amount, currency")
            .eq("user_id", user_id)
            .eq("type", "dividend")
            .execute()
        )
        totals: dict = {"KRW": 0.0, "USD": 0.0}
        for t in response.data:
            cur = t.get("currency", "KRW")
            amount = t.get("dividend_amount")
            if amount is None:
                amount = float(t.get("quantity", 0))
            totals[cur] = totals.get(cur, 0.0) + float(amount)
        return totals
    except Exception:
        return {"KRW": 0.0, "USD": 0.0}
