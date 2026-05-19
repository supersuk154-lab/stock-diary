import streamlit as st
import datetime
from prices import _market_time_bucket, TICKER_MAP, get_realtime_prices_bulk, get_usd_to_krw
from db import get_real_inventory, get_dividend_total
from ui_components import banner

KR_MIN_WAGE_2026 = 10_320

def _get_active_wage() -> int:
    try:
        if "_custom_wage" in st.session_state:
            return int(st.session_state["_custom_wage"])
    except Exception:
        pass
    try:
        return int(st.secrets.get("MY_HOURLY_WAGE", KR_MIN_WAGE_2026))
    except Exception:
        return KR_MIN_WAGE_2026


@st.cache_data(ttl=60)
def get_dividend_work_stats(user_id: str, hourly_wage: int, _supabase) -> dict:
    """배당금을 알바 노동시간으로 환산한다.

    Returns:
        {
            "total_krw_equiv":     누적 배당의 KRW 환산 총합,
            "daily_avg_krw":       일 평균 배당(KRW),
            "daily_work_minutes":  일 평균 알바 시간(분),
            "total_work_minutes":  누적 알바 시간(분),
            "days_elapsed":        첫 배당부터 오늘까지 경과 일수,
            "has_data":            배당 기록 존재 여부,
        }
    """
    empty = {
        "total_krw_equiv": 0.0,
        "daily_avg_krw": 0.0,
        "daily_work_minutes": 0.0,
        "total_work_minutes": 0.0,
        "days_elapsed": 0,
        "has_data": False,
    }
    if hourly_wage <= 0:
        return empty

    try:
        # get_dividend_work_stats 에서도 user_id 필터를 적용합니다 (지시서 & 보안 패치)
        response = (
            _supabase.table("trades")
            .select("created_at, quantity, dividend_amount, currency")
            .eq("user_id", user_id)
            .eq("type", "dividend")
            .order("created_at", desc=False)
            .execute()
        )
        rows = response.data
        if not rows:
            return empty

        has_usd = any(r.get("currency") == "USD" for r in rows)
        usd_to_krw = get_usd_to_krw(_market_time_bucket()) if has_usd else 1.0

        total_krw = 0.0
        first_date_str = rows[0]["created_at"][:10]   # YYYY-MM-DD

        for r in rows:
            amount = r.get("dividend_amount")
            if amount is None:
                amount = float(r.get("quantity") or 0)
            cur = r.get("currency", "KRW")
            krw_value = float(amount) * usd_to_krw if cur == "USD" else float(amount)
            total_krw += krw_value

        if total_krw <= 0:
            return empty

        try:
            first_date = datetime.date.fromisoformat(first_date_str)
            days_elapsed = max((datetime.date.today() - first_date).days + 1, 1)
        except Exception:
            days_elapsed = 1

        daily_avg_krw = total_krw / days_elapsed
        total_work_min = (total_krw / hourly_wage) * 60
        daily_work_min = (daily_avg_krw / hourly_wage) * 60

        return {
            "total_krw_equiv": total_krw,
            "daily_avg_krw": daily_avg_krw,
            "daily_work_minutes": daily_work_min,
            "total_work_minutes": total_work_min,
            "days_elapsed": days_elapsed,
            "has_data": True,
        }
    except Exception:
        return empty


def format_work_time(minutes: float) -> str:
    """분 단위 노동시간을 사람이 읽기 좋은 형태로 변환."""
    if minutes < 1:
        return "1분 미만"
    if minutes < 60:
        # pyrefly: ignore [unnecessary-type-conversion]
        return f"{int(round(minutes))}분"
    h_total = minutes / 60
    if h_total < 8:
        h = int(h_total)
        # pyrefly: ignore [unnecessary-type-conversion]
        m = int(round(minutes - h * 60))
        return f"{h}시간 {m}분" if m else f"{h}시간"
    days = int(h_total // 8)
    # pyrefly: ignore [unnecessary-type-conversion]
    rem_h = int(round(h_total - days * 8))
    if rem_h >= 8:
        days += 1
        rem_h = 0
    return f"{days}일 {rem_h}시간 근무" if rem_h else f"{days}일 근무"


def render_fire_countdown(monthly_krw: float):
    """FIRE 마일스톤 카드."""
    milestones = [
        (50_000,    "🥚 주말 카페값 자유",   "주말마다 커피 걱정 끝!"),
        (300_000,   "🐣 고정비 해방",        "통신비 + 넷플릭스 + 헬스장 커버"),
        (1_000_000, "🐤 하프 은퇴",          "최소 생활비 절반 커버"),
        (2_000_000, "🦅 완전한 경제적 자유", "이번 달 일 안 해도 됨!"),
    ]

    prev_goal = 0
    next_goal, next_label, next_desc = milestones[0]
    progress = 0.0
    for goal, label, desc in milestones:
        if monthly_krw < goal:
            next_goal, next_label, next_desc = goal, label, desc
            span = goal - prev_goal
            progress = (monthly_krw - prev_goal) / span if span > 0 else 0.0
            break
        prev_goal = goal
    else:
        next_goal, next_label, next_desc = milestones[-1][0], "🎉 FIRE 졸업", "이미 완벽한 경제적 자유를 달성했습니다!"
        progress = 1.0

    progress = min(max(progress, 0.0), 1.0)
    remaining = max(next_goal - monthly_krw, 0)
    achieved = [label for goal, label, _ in milestones if monthly_krw >= goal]

    st.markdown(
        f'<div style="background:#f8f9fa; border-radius:14px; padding:16px 20px; '
        f'margin-top:10px; border:1px solid #e9ecef;">'
        f'<div style="font-size:0.85em; color:#868e96; font-weight:600; margin-bottom:6px;">⏳ FIRE 카운트다운</div>'
        f'<div style="font-size:1.05em; font-weight:700; color:#339af0; margin-bottom:4px;">{next_label}</div>'
        f'<div style="font-size:0.83em; color:#666; margin-bottom:8px;">{next_desc}</div>'
        f'<div style="font-size:0.8em; color:#495057;">'
        f'예상 월 배당: <b>{monthly_krw:,.0f}원</b>'
        f'{f" · 목표까지 <b>{remaining:,.0f}원</b>" if remaining > 0 else ""}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.progress(progress)
    if achieved:
        st.caption("달성 완료: " + "  ".join(achieved))


def render_family_contributions(portfolio: list, _supabase, user_id: str):
    """주식 가족 분담금 카드."""
    try:
        # render_family_contributions에서도 user_id 필터를 적용하여 보안 강화
        resp = (
            _supabase.table("trades")
            .select("stock_name, dividend_amount, quantity, currency")
            .eq("user_id", user_id)
            .eq("type", "dividend")
            .execute()
        )
        div_by_stock: dict = {}
        for r in resp.data:
            name = r.get("stock_name")
            if not name:
                continue  # [수정 #7] stock_name이 NULL이면 건너뜀
            amount = float(r.get("dividend_amount") or r.get("quantity") or 0)
            div_by_stock[name] = div_by_stock.get(name, 0) + amount

        for item in portfolio:
            if item["종목"] not in div_by_stock:
                div_by_stock[item["종목"]] = 0.0

        if not div_by_stock:
            st.info("아직 가족들이 용돈을 주지 않았어요. 조금 더 기다려볼까요?")
            return

        sorted_stocks = sorted(div_by_stock.items(), key=lambda x: x[1], reverse=True)
        total_div = sum(v for _, v in sorted_stocks if v > 0)

        rows_html = ""
        for idx, (name, amount) in enumerate(sorted_stocks):
            if amount == 0:
                role, color = "취준생 둘째 🎧", "#adb5bd"
                comment = "아직은 무직이지만 열심히 성장 중. 언젠가 일해줄 거예요!"
                amount_str = "아직 없음"
                pct_html = ""
            elif idx == 0:
                role, color = "든든한 맏형 🧑‍💼", "#339af0"
                comment = "우리 집 기둥! 가장 많은 생활비를 보태주고 있어요."
                amount_str = f"{amount:,.0f}원"
                pct = amount / total_div * 100 if total_div > 0 else 0
                pct_html = f'<div style="font-size:0.75em;color:#adb5bd;margin-top:3px;">전체 배당의 {pct:.1f}%</div>'
            elif any(k in name for k in ("KODEX", "TIGER", "ARIRANG", "KBSTAR", "HANARO")):
                role, color = "야무진 막내 👶", "#51cf66"
                comment = "매달 꼬박꼬박 잊지 않고 효도하는 중!"
                amount_str = f"{amount:,.0f}원"
                pct = amount / total_div * 100 if total_div > 0 else 0
                pct_html = f'<div style="font-size:0.75em;color:#adb5bd;margin-top:3px;">전체 배당의 {pct:.1f}%</div>'
            else:
                role, color = "성실한 식구 👨‍🌾", "#94d82d"
                comment = "묵묵히 자기 몫의 분담금을 내고 있습니다."
                amount_str = f"{amount:,.0f}원"
                pct = amount / total_div * 100 if total_div > 0 else 0
                pct_html = f'<div style="font-size:0.75em;color:#adb5bd;margin-top:3px;">전체 배당의 {pct:.1f}%</div>'

            rows_html += (
                f'<div style="padding:12px 16px; margin-bottom:8px; background:#fff; '
                f'border-radius:10px; border-left:4px solid {color}; '
                f'box-shadow:0 1px 4px rgba(0,0,0,0.04);">'
                f'<div style="font-weight:700; color:#212529;">{name} '
                f'<span style="font-size:0.83em; color:#888; font-weight:400;">({role})</span></div>'
                f'<div style="display:flex; justify-content:space-between; margin-top:5px; align-items:center;">'
                f'<span style="font-size:0.82em; color:#666;">{comment}</span>'
                f'<span style="font-weight:700; color:#2b8a3e; font-size:0.88em;">{amount_str}</span>'
                f'</div>{pct_html}</div>'
            )

        st.markdown(rows_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"가족 분담금 조회 실패: {e}")


def get_daily_meal(daily_avg_krw: float) -> dict:
    """일 평균 배당금을 보편적인 식사/간식 메뉴로 변환."""
    if daily_avg_krw < 500:
        return {"icon": "🍬", "menu": "사탕 한 알", "desc": "아직은 작지만, 매일 쌓이면 달라집니다."}
    elif daily_avg_krw < 1500:
        return {"icon": "☕", "menu": "편의점 커피", "desc": "오늘도 자산이 커피 한 잔을 쐈습니다!"}
    elif daily_avg_krw < 3000:
        return {"icon": "🥐", "menu": "아메리카노 + 크루아상", "desc": "아침 카페 비용을 자산이 내주고 있어요."}
    elif daily_avg_krw < 6000:
        return {"icon": "🍜", "menu": "편의점 도시락", "desc": "점심 한 끼 값을 주식이 내줍니다."}
    elif daily_avg_krw < 10000:
        return {"icon": "🍱", "menu": "한식 백반", "desc": "매일 든든한 점심을 자산이 책임집니다."}
    elif daily_avg_krw < 20000:
        return {"icon": "🍖", "menu": "고기 정식", "desc": "오늘은 자산 덕분에 고기 한 판 먹을 수 있어요!"}
    elif daily_avg_krw < 50000:
        return {"icon": "🥩", "menu": "한우 한 점", "desc": "자산이 매일 한우를 사줍니다. 대단한 페이스입니다!"}
    else:
        return {"icon": "🍽️", "menu": "파인다이닝 코스", "desc": "자산이 매일 파인다이닝을 선물합니다. 진정한 FIRE!"}


def render_inventory_section(supabase, user_id: str, zen_mode: bool):
    """나의 보물함 실시간 주가 연동 및 배당 통계 렌더링."""
    st.markdown("### 📦 나의 보물함 (실시간)")
    
    if zen_mode:
        st.info("🌿 **동굴 대피 중**\n\n회원님이 지금까지 땀 흘려 모은 우량 자산들은 계좌에 안전하게 보관되어 있습니다. 오늘은 주가를 잊고 본업에 집중해 보세요!")
    else:
        my_portfolio = get_real_inventory(user_id, supabase)
    
        if not my_portfolio:
            st.info("아직 텅 비어있네요! 💸 이번 달은 삼성전자나 Alphabet 같은 든든한 자산을 모아 첫 기록을 남겨보는 건 어떨까요?")
        else:
            all_tickers = tuple(
                TICKER_MAP[item["종목"]]
                for item in my_portfolio
                if item["종목"] in TICKER_MAP
            )
            _tb = _market_time_bucket()
            bulk_prices = get_realtime_prices_bulk(all_tickers, time_bucket=_tb) if all_tickers else {}
            usd_rate = get_usd_to_krw(time_bucket=_tb)
    
            # 총 평가 자산 계산
            total_krw = 0.0
            all_priced = True
            for _item in my_portfolio:
                # pyrefly: ignore [bad-argument-type]
                _ticker = TICKER_MAP.get(_item["종목"])
                _price = bulk_prices.get(_ticker) if _ticker else None
                if _price and _item["수량"] > 0:
                    if _item["통화"] == "KRW":
                        total_krw += _price * _item["수량"]
                    else:
                        total_krw += _price * _item["수량"] * usd_rate
                else:
                    all_priced = False
    
            if total_krw > 0:
                _note = "" if all_priced else " <span style='font-size:0.7em;opacity:0.75;'>(일부 종목 제외)</span>"
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#3182F6 0%,#1a6fd8 100%);
                            border-radius:16px; padding:20px 24px; margin-bottom:16px; color:white;">
                    <div style="font-size:0.82em; opacity:0.85;">총 평가 자산{_note}</div>
                    <div style="font-size:1.65em; font-weight:800; margin:4px 0; letter-spacing:-0.5px;">
                        {total_krw:,.0f}원</div>
                    <div style="font-size:0.78em; opacity:0.7;">환율 적용: 1$ = {usd_rate:,.0f}원</div>
                </div>""", unsafe_allow_html=True)
    
            rows_html = ""
            for item in my_portfolio:
                # pyrefly: ignore [bad-argument-type]
                ticker = TICKER_MAP.get(item["종목"])
                current_price = bulk_prices.get(ticker) if ticker else None
                has_valid_price = current_price is not None and current_price > 0
                currency = "원" if item["통화"] == "KRW" else "$"
    
                if has_valid_price:
                    price_str = f"{current_price:,.0f}" if item["통화"] == "KRW" else f"{current_price:,.2f}"
                    price_html = f'<span style="font-weight:700; font-size:1.05em; color:#191F28;">{price_str}{currency}</span>'
                elif item["평단가"] > 0:
                    avg_str = f"{item['평단가']:,.0f}" if item["통화"] == "KRW" else f"{item['평단가']:,.2f}"
                    price_html = (f'<span style="font-weight:700; font-size:1.05em; color:#8B95A1;">'
                                  f'{avg_str}{currency}</span>'
                                  f'<span style="font-size:0.72em; color:#B0B8C1;"> (지연됨 📡)</span>')
                else:
                    price_html = '<span style="font-weight:600; font-size:0.9em; color:#8B95A1;">수신 지연 📡</span>'
    
                if has_valid_price and item["평단가"] > 0:
                    profit_rate = ((current_price - item["평단가"]) / item["평단가"]) * 100
                    sign = "+" if profit_rate > 0 else ""
                    if profit_rate > 0:
                        rate_color = "#F04452"
                    elif profit_rate < 0:
                        rate_color = "#3182F6"
                    else:
                        rate_color = "#8B95A1"
                    rate_html = f'<span style="color:{rate_color}; font-weight:600; font-size:0.85em;">{sign}{profit_rate:.2f}%</span>'
                elif not ticker:
                    rate_html = '<span style="color:#B0B8C1; font-size:0.8em;">티커 미등록</span>'
                else:
                    rate_html = '<span style="color:#B0B8C1; font-size:0.8em;">단가 미기록</span>'
    
                rows_html += f"""
                <div style="display:flex; justify-content:space-between; align-items:center;
                            padding:16px; border-radius:16px; margin-bottom:12px;
                            background-color:#FFFFFF; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
                            border: 1px solid #F2F4F6;">
                    <div style="line-height:1.4; flex: 1; min-width: 0; padding-right: 16px;">
                        <div style="font-weight:700; font-size:1.05em; color:#333D4B; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;" title="{item['종목']}">{item['종목']}</div>
                        <div style="color:#8B95A1; font-size:0.85em; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">{item['수량']:,.0f}주 보유</div>
                    </div>
                    <div style="text-align:right; line-height:1.4; flex-shrink: 0;">
                        <div>{price_html}</div>
                        <div>{rate_html}</div>
                    </div>
                </div>"""
    
            st.markdown(rows_html, unsafe_allow_html=True)
            st.caption("💡 '티커 미등록' 종목은 app.py의 TICKER_MAP에 야후파이낸스 코드를 추가하면 실시간 연동됩니다.")
    
            # 누적 배당금 요약
            div_totals = get_dividend_total(user_id, supabase)
            div_parts = []
            if div_totals.get("KRW", 0) > 0:
                div_parts.append(f"🇰🇷 {div_totals['KRW']:,.0f}원")
            if div_totals.get("USD", 0) > 0:
                div_parts.append(f"🇺🇸 ${div_totals['USD']:,.2f}")
            if div_parts:
                st.markdown(
                    f'<div style="background:#F0FDF4; border-radius:12px; padding:12px 16px; '
                    f'margin-top:4px; font-size:0.9em; color:#166534;">'
                    f'🍯 누적 배당금: <b>{" + ".join(div_parts)}</b></div>',
                    unsafe_allow_html=True
                )
    
            # 오늘의 알바생
            _active_wage = _get_active_wage()
            work_stats = get_dividend_work_stats(
                user_id,
                _active_wage,
                supabase,
            )
    
            if not work_stats["has_data"]:
                st.markdown(
                    '<div style="background: linear-gradient(135deg, #F1F5F915, #E2E8F015); '
                    'border:1px dashed #CBD5E1; border-radius:14px; padding:14px 18px; margin-top:10px;">'
                    '<div style="font-size:0.85em; color:#64748B;">🧑‍💼 오늘의 알바생</div>'
                    '<div style="font-size:0.95em; margin-top:4px; color:#94A3B8;">'
                    '아직 잠자고 있어요 💤  첫 배당이 들어오면 일을 시작합니다.'
                    '</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                daily_min = work_stats["daily_work_minutes"]
                total_min = work_stats["total_work_minutes"]
                daily_krw = work_stats["daily_avg_krw"]
                elapsed   = work_stats["days_elapsed"]
    
                if daily_min < 3:
                    daily_phrase = "잠깐 심부름 다녀온 정도"
                    emoji = "🚶"
                elif daily_min < 15:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 알바 완료"
                    emoji = "🧑‍🔧"
                elif daily_min < 60:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 알바 뛰어줌"
                    emoji = "💼"
                elif daily_min < 240:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 파트타임 근무"
                    emoji = "🏃"
                elif daily_min < 480:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 풀타임에 근접"
                    emoji = "🔥"
                else:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 정직원급 근무"
                    emoji = "🚀"
    
                wage_note = (
                    f"본인 시급 {_active_wage:,}원 기준"
                    if _active_wage != KR_MIN_WAGE_2026
                    else f"2026년 최저시급 {KR_MIN_WAGE_2026:,}원 기준"
                )
    
                st.markdown(
                    f'<div style="background: linear-gradient(135deg, #EEF2FF, #FAF5FF); '
                    f'border-radius:14px; padding:16px 20px; margin-top:10px;">'
                    f'<div style="font-size:0.85em; color:#6366F1; font-weight:600;">'
                    f'{emoji} 오늘의 알바생</div>'
                    f'<div style="font-size:1.08em; margin-top:6px; color:#1E293B; line-height:1.5;">'
                    f'내 주식이 매일 평균 {daily_phrase}'
                    f'</div>'
                    f'<div style="font-size:0.78em; color:#64748B; margin-top:8px;">'
                    f'일 평균 {daily_krw:,.0f}원  ·  누적 노동시간 '
                    f'<b>{format_work_time(total_min)}</b>  ·  {elapsed}일째 출근 중'
                    f'</div>'
                    f'<div style="font-size:0.72em; color:#94A3B8; margin-top:4px;">'
                    f'{wage_note}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
    
                with st.expander("⚙️ 내 시급으로 환산하기", expanded=False):
                    st.caption(
                        "본인의 실제 시급을 기준으로 환산하면 임팩트가 훨씬 커집니다. "
                        "영구 저장하려면 `.streamlit/secrets.toml`에 "
                        "`MY_HOURLY_WAGE = 25000` 같이 추가하세요."
                    )
                    new_wage = st.number_input(
                        "이번 세션에서만 적용할 시급(원)",
                        min_value=1_000,
                        max_value=500_000,
                        value=_active_wage,
                        step=500,
                        key="custom_wage_input",
                    )
                    if st.button("이 세션에 적용", key="apply_custom_wage"):
                        get_dividend_work_stats.clear()
                        st.session_state["_custom_wage"] = new_wage
                        st.rerun()
    
                meal = get_daily_meal(daily_krw)
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#ffffff,#f8f9fa); '
                    f'border-radius:14px; padding:16px 20px; margin-top:10px; border:1px solid #e9ecef;">'
                    f'<div style="font-size:0.85em; color:#868e96; font-weight:600;">🍽️ 오늘의 자산 식탁</div>'
                    f'<div style="text-align:center; margin:10px 0;">'
                    f'<div style="font-size:2.4rem;">{meal["icon"]}</div>'
                    f'<div style="font-size:1.05em; font-weight:700; color:#212529; margin-top:6px;">{meal["menu"]}</div>'
                    f'<div style="font-size:0.85em; color:#495057; margin-top:5px;">{meal["desc"]}</div>'
                    f'</div>'
                    f'<div style="border-top:1px dashed #dee2e6; padding-top:8px; text-align:center; '
                    f'font-size:0.82em; color:#868e96;">'
                    f'일 평균 배당: <b style="color:#339af0;">{daily_krw:,.0f}원</b>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
    
                render_fire_countdown(daily_krw * 30.4)
    
            with st.expander("🏠 우리 집 주식 가족 분담금", expanded=False):
                render_family_contributions(my_portfolio, supabase, user_id)
    
        with st.expander("🍯 배당금 직접 기록하기", expanded=False):
            with st.form("dividend_form", clear_on_submit=True):
                col_dname, col_damount = st.columns([2, 1])
                with col_dname:
                    div_stock = st.text_input("종목명", placeholder="예: 삼성전자")
                with col_damount:
                    div_amount = st.number_input("배당금 금액", min_value=0.0, step=100.0)
                div_currency = st.radio("통화", ["KRW", "USD"], horizontal=True)
                div_submit = st.form_submit_button("💰 배당금 기록 저장", type="primary")
    
                if div_submit and div_stock and div_amount > 0:
                    try:
                        supabase.table("trades").insert({
                            "user_id":         user_id,
                            "stock_name":      div_stock.strip(),
                            "quantity":        0.0,
                            "price":           0.0,
                            "currency":        div_currency,
                            "type":            "dividend",
                            "dividend_amount": div_amount
                        }).execute()
                        get_dividend_total.clear()
                        _sym = "원" if div_currency == "KRW" else "$"
                        st.success(f"✅ {div_stock.strip()} 배당금 {div_amount:,.0f}{_sym} 기록 완료!")
                    except Exception as _e:
                        st.error(f"저장 실패: {_e}")
