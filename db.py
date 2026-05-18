import datetime
from datetime import timezone, timedelta
import streamlit as st

KST = timezone(timedelta(hours=9))


def to_kst_str(iso_ts: str) -> str:
    """Postgres timestamptz → 'YYYY-MM-DD HH:MM:SS' (KST)"""
    if not iso_ts:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_ts


def calculate_scores(supabase):
    """최근 30일 일기를 기반으로 투자 능력치 점수를 계산."""
    thirty_days_ago = (
        datetime.datetime.now(timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()

    try:
        response = (
            supabase.table("journals")
            .select("created_at, tags")
            .gte("created_at", thirty_days_ago)
            .order("created_at", desc=True)
            .execute()
        )
        rows = response.data
    except Exception as e:
        st.sidebar.warning(f"점수 조회 실패: {e}")
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


def get_past_context(tags, supabase):
    """현재 선택된 태그 중 가장 중요한 감정 태그를 찾아 과거 일기를 소환."""
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
            supabase.table("journals")
            .select("created_at, content")
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


@st.cache_data(ttl=10)
def get_recent_journals(user_id: str, _supabase, limit: int = 50):
    """user_id를 캐시 키에 포함해서 사용자별로 분리된 캐시를 사용."""
    try:
        response = (
            _supabase.table("journals")
            .select("id, created_at, tags, content, ai_feedback")
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
    """trades 테이블에서 매수 내역을 가져와 종목별 총 수량과 평단가를 계산.
    type='dividend' 행은 재고 계산에서 제외."""
    try:
        response = (
            _supabase.table("trades")
            .select("stock_name, quantity, price, currency, type")
            .or_("type.eq.buy,type.is.null")
            .execute()
        )
        trades = response.data

        if not trades:
            return []

        inventory_map = {}
        for t in trades:
            name = t.get("stock_name")
            qty = float(t.get("quantity", 0))
            price = float(t.get("price") or 0)
            currency = t.get("currency", "KRW")

            if not name or qty <= 0:
                continue

            if name not in inventory_map:
                inventory_map[name] = {"총수량": 0, "총금액": 0, "통화": currency}

            inventory_map[name]["총수량"] += qty
            inventory_map[name]["총금액"] += (qty * price)

        result = []
        for name, data in inventory_map.items():
            if data["총수량"] > 0:
                avg_price = data["총금액"] / data["총수량"]
                result.append({
                    "종목": name,
                    "수량": data["총수량"],
                    "평단가": avg_price,
                    "통화": data["통화"]
                })
        return result

    except Exception as e:
        st.error(f"재고 데이터 집계 실패: {e}")
        return []


@st.cache_data(ttl=30)
def get_dividend_total(user_id: str, _supabase) -> dict:
    """배당금 합계 조회. {"KRW": 원화합계, "USD": 달러합계} 형태로 반환."""
    try:
        response = (
            _supabase.table("trades")
            .select("quantity, currency")
            .eq("type", "dividend")
            .execute()
        )
        totals: dict = {"KRW": 0.0, "USD": 0.0}
        for t in response.data:
            cur = t.get("currency", "KRW")
            totals[cur] = totals.get(cur, 0.0) + float(t.get("quantity", 0))
        return totals
    except Exception:
        return {"KRW": 0.0, "USD": 0.0}
