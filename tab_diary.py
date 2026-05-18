import streamlit as st
import datetime
from PIL import Image, ImageDraw
import os

from prices import get_market_weather, _market_time_bucket, TICKER_MAP, get_realtime_price, get_realtime_prices_bulk, get_usd_to_krw
from db import KST, get_past_context, has_tag, get_real_inventory, get_dividend_total, calculate_scores, get_recent_journals
from ai_helper import safe_generate
from ui_components import render_radar_chart, banner, card

KR_MIN_WAGE_2026 = 10_320
MODEL_NAME = "gemini-3.1-flash-lite-preview"

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


# ==========================================
# 🧑‍💼 "오늘의 알바생" — 배당금을 알바 노동시간으로 환산
# ==========================================
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
        response = (
            _supabase.table("trades")
            .select("created_at, quantity, dividend_amount, currency")
            .eq("type", "dividend")
            .order("created_at", desc=False)
            .execute()
        )
        rows = response.data
        if not rows:
            return empty

        # USD 배당이 있을 때만 환율 조회 (불필요한 API 호출 방지)
        has_usd = any(r.get("currency") == "USD" for r in rows)
        usd_to_krw = get_usd_to_krw(_market_time_bucket()) if has_usd else 1.0

        total_krw = 0.0
        first_date_str = rows[0]["created_at"][:10]   # YYYY-MM-DD

        for r in rows:
            # 신구 데이터 호환: dividend_amount 우선, 없으면 과거 quantity
            amount = r.get("dividend_amount")
            if amount is None:
                amount = float(r.get("quantity") or 0)
            cur = r.get("currency", "KRW")
            krw_value = float(amount) * usd_to_krw if cur == "USD" else float(amount)
            total_krw += krw_value

        if total_krw <= 0:
            return empty

        # 기간 계산 (첫 배당일 ~ 오늘, 최소 1일 보정)
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
        return f"{int(round(minutes))}분"
    h_total = minutes / 60
    if h_total < 8:   # 하루 풀타임(8시간) 미만
        h = int(h_total)
        m = int(round(minutes - h * 60))
        return f"{h}시간 {m}분" if m else f"{h}시간"
    # 8시간 이상은 "일" 단위로
    days = int(h_total // 8)
    rem_h = int(round(h_total - days * 8))
    if rem_h >= 8:   # 반올림 보정
        days += 1
        rem_h = 0
    return f"{days}일 {rem_h}시간 근무" if rem_h else f"{days}일 근무"


def render_fire_countdown(monthly_krw: float):
    """FIRE 마일스톤 카드. monthly_krw: 예상 월 배당수입(원)"""
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


def render_family_contributions(portfolio: list, _supabase):
    """주식 가족 분담금 카드. portfolio: get_real_inventory() 결과."""
    try:
        resp = (
            _supabase.table("trades")
            .select("stock_name, dividend_amount, quantity, currency")
            .eq("type", "dividend")
            .execute()
        )
        div_by_stock: dict = {}
        for r in resp.data:
            name = r.get("stock_name")
            amount = float(r.get("dividend_amount") or r.get("quantity") or 0)
            div_by_stock[name] = div_by_stock.get(name, 0) + amount

        # 포트폴리오 종목 중 배당 기록이 없는 종목 → 취준생으로 표시
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


def render_diary_tab(supabase, ai_client, dev_mode):
    def sync_mentor():
        mentor = st.session_state.get("persona_widget")
        if mentor:
            st.session_state["chosen_mentor"] = mentor
            try:
                supabase.auth.update_user({"data": {"chosen_mentor": mentor}})
            except Exception:
                pass

    # ==========================================
    # 🦇 [신규] 동굴 모드 (Zen Mode) 스위치
    # ==========================================
    zen_mode = st.sidebar.toggle(
        "🦇 동굴 모드 켜기",
        value=False,
        help="시장이 폭락해 멘탈이 흔들릴 때 켜세요. 모든 수익률과 숫자를 가려줍니다."
    )

    
    # ---------------------------------------------------------
    # 🌤️ 증시 날씨판 — zen_mode 일 땐 숨김
    # ---------------------------------------------------------
    if not zen_mode:
        _weather = get_market_weather(time_bucket=_market_time_bucket())
        _weather_items = list(_weather.items())
        _row1, _row2 = _weather_items[:2], _weather_items[2:]
        for _row in (_row1, _row2):
            _cols = st.columns(2)
            for _col, (name, data) in zip(_cols, _row):
                with _col:
                    if data:
                        pct = data["change_pct"]
                        curr = data["current"]
                        if pct > 0:
                            color, icon, arrow = "#e03131", "☀️", "▲"
                        elif pct < 0:
                            color, icon, arrow = "#1c7ed6", "☔", "▼"
                        else:
                            color, icon, arrow = "#868e96", "☁️", "–"
                        st.markdown(
                            f'<div style="background:#f8f9fa; border-radius:10px; padding:12px; '
                            f'text-align:center; border:1px solid #e9ecef; margin-bottom:8px;">'
                            f'<div style="font-size:0.8em; color:#495057; font-weight:600;">{name} {icon}</div>'
                            f'<div style="font-size:1.15em; font-weight:800; margin:4px 0;">{curr:,.2f}</div>'
                            f'<div style="font-size:0.9em; font-weight:700; color:{color};">'
                            f'{arrow} {abs(pct):.2f}%</div></div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div style="background:#f8f9fa; border-radius:10px; padding:12px; '
                            f'text-align:center; border:1px solid #e9ecef; margin-bottom:8px;">'
                            f'<div style="font-size:0.8em; color:#495057; font-weight:600;">{name}</div>'
                            f'<div style="font-size:0.85em; color:#adb5bd; margin-top:8px;">💤 수신 지연</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
        st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)
    
    # ---------------------------------------------------------
    # 📱 1. 오늘의 멘토 설정 (아코디언)
    #   - expander 헤더 자체에 현재 멘토 상태를 표시해서
    #     접혀 있어도 한눈에 알 수 있게 함
    # ---------------------------------------------------------
    _current_mentor = st.session_state.get("chosen_mentor")
    if _current_mentor:
        _expander_label = f"🤖 오늘의 멘토 설정  ·  ✅ {_current_mentor}"
    else:
        _expander_label = "🤖 오늘의 멘토 설정  ·  ⚠️ 멘토가 설정되지 않았습니다 (터치하여 선택)"
    
    with st.expander(_expander_label, expanded=not zen_mode):
        if zen_mode:
            st.success("🧘‍♂️ **마음의 평화 모드 작동 중**\n\n숫자와 차트는 잠시 가려두었습니다. 심호흡을 하고 일기를 써보세요.")
            options = ["☕ 따뜻한 심리 상담가 (공감/위로)", "🤖 정중한 AI 비서 (기본/깔끔)", "🤝 다정한 주식 찐친 (유쾌한 반말)", "🧊 팩트폭행 1타 강사 (단호/원칙)"]
        else:
            options = ["🤖 정중한 AI 비서 (기본/깔끔)", "☕ 따뜻한 심리 상담가 (공감/위로)", "🤝 다정한 주식 찐친 (유쾌한 반말)", "🧊 팩트폭행 1타 강사 (단호/원칙)"]
        
        # 안전 금고에 값이 있으면 그 인덱스를 유지, 없으면 None(초기 미지정 상태)
        saved_mentor = st.session_state.get("chosen_mentor")
        default_index = options.index(saved_mentor) if saved_mentor in options else None
    
        # [수정] 콜백 함수(on_change)를 붙여 선택 즉시 메모리에 박제합니다.
        st.selectbox(
            "오늘의 멘토를 선택하세요",
            options=options,
            index=default_index,
            placeholder="⚠️ 멘토가 설정되지 않았습니다 (터치해서 선택)",
            key="persona_widget",
            on_change=sync_mentor,
            label_visibility="collapsed"
        )
        
    
    # [추가] 멘토 설정 상태를 expander 외부 하단에도 명시
    # (expander가 접혀 있어도 현재 설정 여부를 두 번 확인 가능)
    if st.session_state.get("chosen_mentor"):
        st.success(f"✅ **{st.session_state['chosen_mentor']}**(으)로 설정되었습니다. 든든한 조언을 기대해주세요!")
    else:
        st.warning("⚠️ **멘토가 설정되지 않았습니다.** 위 '🤖 오늘의 멘토 설정' 창을 터치하여 오늘 대화할 멘토를 골라주세요.")
    
    # ---------------------------------------------------------
    # 📦 2. 나의 보물함 (Inventory) - 실시간 주가 연동
    # ---------------------------------------------------------
    st.markdown("### 📦 나의 보물함 (실시간)")
    
    if zen_mode:
        # [동굴 모드 ON] 숫자를 모두 가리고 평온한 메시지 출력
        st.info("🌿 **동굴 대피 중**\n\n회원님이 지금까지 땀 흘려 모은 우량 자산들은 계좌에 안전하게 보관되어 있습니다. 오늘은 주가를 잊고 본업에 집중해 보세요!")
        
    else:
        # [핵심] 가짜 데이터 대신 Supabase DB에서 집계된 진짜 재고를 불러옴
        my_portfolio = get_real_inventory(st.session_state["user_id"], supabase)
    
        if not my_portfolio:
            st.info("아직 텅 비어있네요! 💸 이번 달은 삼성전자나 Alphabet 같은 든든한 자산을 모아 첫 기록을 남겨보는 건 어떨까요?")
        else:
            # 필요한 티커를 모아 한 번에 일괄 조회
            all_tickers = tuple(
                TICKER_MAP[item["종목"]]
                for item in my_portfolio
                if item["종목"] in TICKER_MAP
            )
            _tb = _market_time_bucket()
            bulk_prices = get_realtime_prices_bulk(all_tickers, time_bucket=_tb) if all_tickers else {}
            usd_rate = get_usd_to_krw(time_bucket=_tb)
    
            # ── 총 평가 자산 계산 ──────────────────────────────────────
            total_krw = 0.0
            all_priced = True
            for _item in my_portfolio:
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
                ticker = TICKER_MAP.get(item["종목"])
                current_price = bulk_prices.get(ticker) if ticker else None
                has_valid_price = current_price is not None and current_price > 0
                currency = "원" if item["통화"] == "KRW" else "$"
    
                # 1. 오른쪽 상단: 현재가 또는 평단가(지연됨) 폴백
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
    
                # 2. 오른쪽 하단: 수익률 또는 상태 표시
                if has_valid_price and item["평단가"] > 0:
                    profit_rate = ((current_price - item["평단가"]) / item["평단가"]) * 100
                    sign = "+" if profit_rate > 0 else ""
                    # 토스 스타일 증권 색상: 빨강(상승), 파랑(하락), 회색(보합)
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
    
                # 3. 모바일 앱 스타일의 하얀색 카드(Card) UI 렌더링
                rows_html += f"""
                <div style="display:flex; justify-content:space-between; align-items:center;
                            padding:16px; border-radius:16px; margin-bottom:12px;
                            background-color:#FFFFFF; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
                            border: 1px solid #F2F4F6;">
                    <div style="line-height:1.4;">
                        <div style="font-weight:700; font-size:1.05em; color:#333D4B;">{item['종목']}</div>
                        <div style="color:#8B95A1; font-size:0.85em;">{item['수량']:,.0f}주 보유</div>
                    </div>
                    <div style="text-align:right; line-height:1.4;">
                        <div>{price_html}</div>
                        <div>{rate_html}</div>
                    </div>
                </div>"""
    
            st.markdown(rows_html, unsafe_allow_html=True)
            st.caption("💡 '티커 미등록' 종목은 app.py의 TICKER_MAP에 야후파이낸스 코드를 추가하면 실시간 연동됩니다.")
    
            # ── 누적 배당금 요약 ─────────────────────────────────────
            div_totals = get_dividend_total(st.session_state["user_id"], supabase)
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
    
            # ============================================================
            # 🧑‍💼 오늘의 알바생 — 배당금을 노동시간으로 환산
            # ============================================================
            _active_wage = _get_active_wage()
            work_stats = get_dividend_work_stats(
                st.session_state["user_id"],
                _active_wage,
                supabase,
            )
    
            if not work_stats["has_data"]:
                # 빈 상태: 첫 배당 들어오기 전
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
    
                # 일 평균 워딩 — 작은 숫자에도 의미 주기
                if daily_min < 3:
                    daily_phrase = "잠깐 심부름 다녀온 정도"
                    emoji = "🚶"
                elif daily_min < 15:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 알바 완료"
                    emoji = "🧑‍🔧"
                elif daily_min < 60:
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 알바 뛰어줌"
                    emoji = "💼"
                elif daily_min < 240:   # 4시간 미만
                    daily_phrase = f"<b>{format_work_time(daily_min)}</b> 파트타임 근무"
                    emoji = "🏃"
                elif daily_min < 480:   # 8시간 미만
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
    
                # 본인 시급 설정 (선택)
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
    
                # ── 자산이 차린 식탁 ──────────────────────────────────
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
    
                # ── FIRE 카운트다운 ────────────────────────────────────
                render_fire_countdown(daily_krw * 30.4)
    
            # ── 가족 분담금 (배당 있는 경우에만) ─────────────────────
            with st.expander("🏠 우리 집 주식 가족 분담금", expanded=False):
                render_family_contributions(my_portfolio, supabase)
    
        # ── 배당금 직접 기록 폼 ──────────────────────────────────────
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
                            "user_id":         st.session_state["user_id"],
                            "stock_name":      div_stock.strip(),
                            "quantity":        0.0, # 더 이상 배당금을 수량에 욱여넣지 않음
                            "price":           0.0, # 더미 값 제거
                            "currency":        div_currency,
                            "type":            "dividend",
                            "dividend_amount": div_amount # 신규 컬럼에 명확히 적재
                        }).execute()
                        get_dividend_total.clear()
                        _sym = "원" if div_currency == "KRW" else "$"
                        st.success(f"✅ {div_stock.strip()} 배당금 {div_amount:,.0f}{_sym} 기록 완료!")
                    except Exception as _e:
                        st.error(f"저장 실패: {_e}")
    
    st.markdown("---")
    
    # 태그 선택 UI
    st.markdown("### 🏷️ 오늘의 상태 (터치해서 선택)")
    
    st.caption("🏃‍♂️ 나의 투자 루틴 (가점)")
    routine_tags = st.pills("루틴", ["💸 #월급날정기매수", "🍯 #배당금달달해", "🎯 #과거의나칭찬해"],
                            label_visibility="collapsed", selection_mode="multi")
    
    st.caption("🛡️ 멘탈 방어 성공 (가점)")
    defense_tags = st.pills("방어", ["🧘‍♂️ #존버는승리한다", "🙈 #오늘은안봤다", "☕ #한템포쉬어가기"],
                            label_visibility="collapsed", selection_mode="multi")
    
    st.caption("🚨 감정 및 반성 (AI 멘토링)")
    emotion_tags = st.pills("감정", ["😱 #오늘좀흔들", "💸 #뇌동매매반성", "📝 #오늘의실수"],
                            label_visibility="collapsed", selection_mode="multi")
    
    selected_tags = (routine_tags or []) + (defense_tags or []) + (emotion_tags or [])
    
    # 태그 변경 시 채팅 초기화
    if selected_tags != st.session_state.get('current_tags', []):
        st.session_state['current_tags'] = selected_tags
        if selected_tags:
            tags_str = ", ".join(selected_tags)
            st.session_state['chat_messages'] = [
                {"role": "assistant",
                 "content": f"선택하신 **{tags_str}** 태그에 대해 이야기해 볼까요? 오늘 어떤 생각으로 이 상태를 고르셨는지 편하게 들려주세요."}
            ]
        else:
            st.session_state['chat_messages'] = []
        st.rerun()
    
    st.markdown("---")
    
    # ==========================================
    # 💬 [개편] 마음 상태 입력 + AI 멘토와 자유 대화
    #   - 태그 아래 바로 보이는 인라인 입력창
    #   - 대화 히스토리가 입력창 위에 누적됨
    #   - 멘토 페르소나(chosen_mentor)를 말투에 반영
    # ==========================================
    st.subheader("💬 지금 내 마음 상태 이야기하기")
    
    if not selected_tags:
        st.info("👆 위에서 마음에 맞는 태그를 **1개 이상** 골라주세요. 그러면 아래에 AI 멘토와 대화할 수 있는 창이 열립니다.")
    else:
        st.caption("선택한 태그를 보고 AI 멘토가 먼저 말을 걸어줍니다. 자유롭게 답하면서 마음을 정리해보세요.")
    
        # 1) 대화 히스토리 표시 (입력창 위에 누적)
        for msg in st.session_state.get('chat_messages', []):
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
    
        # 2) 인라인 입력 폼 (st.chat_input은 페이지 맨 아래에 고정되어 안 보일 수 있으므로
        #    text_area + 버튼 조합으로 태그 바로 아래에 명확히 표시)
        with st.form("mind_chat_form", clear_on_submit=True):
            user_input = st.text_area(
                "💭 지금 내 심정을 자유롭게 적어보세요",
                placeholder="예) 시장이 흔들려서 마음이 너무 불안해요. 그냥 다 팔아버리고 싶은데 어떡하죠?",
                height=110,
                key="mind_chat_input",
            )
            col_send, col_clear = st.columns([7, 3])
            with col_send:
                send_clicked = st.form_submit_button("💌 AI 멘토에게 보내기", type="primary", use_container_width=True)
            with col_clear:
                clear_clicked = st.form_submit_button("🔄 대화 초기화", use_container_width=True)
    
        if clear_clicked:
            tags_str = ", ".join(selected_tags)
            st.session_state['chat_messages'] = [
                {"role": "assistant",
                 "content": f"선택하신 **{tags_str}** 태그에 대해 다시 이야기해 볼까요? 오늘 어떤 생각이 드는지 편하게 들려주세요."}
            ]
            st.rerun()
    
        if send_clicked and user_input and user_input.strip():
            # 사용자 메시지 저장
            st.session_state['chat_messages'].append(
                {"role": "user", "content": user_input.strip()}
            )
    
            # AI 응답 생성 (대화 히스토리 + 멘토 페르소나 반영)
            with st.spinner("AI 멘토가 답변을 고민 중입니다..."):
                tags_str = ", ".join(selected_tags)
                chosen_mentor = st.session_state.get('chosen_mentor', '')
    
                # 멘토별 말투 지시
                tone_instruction = ""
                if "심리 상담가" in chosen_mentor:
                    tone_instruction = "심리 상담가처럼 매우 따뜻하고 부드러운 존댓말로, 사용자의 감정 자체를 어루만지듯 답하세요."
                elif "주식 찐친" in chosen_mentor:
                    tone_instruction = "10년 지기 동네 친구처럼 편안한 반말로, 친근하고 유쾌하게 위로하면서 답하세요."
                elif "1타 강사" in chosen_mentor:
                    tone_instruction = "깐깐한 일타 강사처럼 단호하고 팩트 위주의 존댓말로, 원칙 준수와 장기 투자의 중요성을 강조하세요."
                else:
                    tone_instruction = "정중하고 깔끔한 존댓말로, 따뜻하면서도 객관적으로 답하세요."
    
                # 최근 대화 8턴까지만 컨텍스트로 사용 (토큰 절약)
                recent_history = st.session_state['chat_messages'][-8:]
                history_text = "\n".join([
                    f"{'사용자' if m['role']=='user' else 'AI 멘토'}: {m['content']}"
                    for m in recent_history
                ])
    
                system_instruction = f"""당신은 장기 투자자의 멘탈을 지켜주는 AI 페이스메이커입니다.
    사용자가 오늘 선택한 감정/상태 태그: {tags_str}
    
    [원칙]
    - 감정은 무죄, 충동적 행동(매도)은 유죄. 사용자의 감정을 비난하지 말고 행동을 막는 데 집중하세요.
    - 짧고 친근하게, 1~3 문단 정도로 답하세요.
    - 마지막엔 짧은 후속 질문 하나로 대화를 이어주세요.
    
    [말투 지시]
    {tone_instruction}
    
    [지금까지의 대화]
    {history_text}
    
    위 대화 흐름에 자연스럽게 이어지도록, 사용자의 가장 최근 메시지에 답해주세요."""
    
                # [변경 후]
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
                
                response_text, err = safe_generate(
                    client=ai_client,
                    model_name=MODEL_NAME,
                    contents=user_input.strip(),
                    config=config,
                    fallback_msg="답변 생성 중 오류가 발생했어요."
                )
    
                if err:
                    st.error(err)
                    response_text = "죄송해요, 잠시 답변을 만들지 못했어요. 잠시 후 다시 보내주세요."
    
                st.session_state['chat_messages'].append(
                    {"role": "assistant", "content": response_text}
                )
    
            st.rerun()
    
    st.markdown("---")
    
    # 1단계: 입력 모드
    if st.session_state['current_step'] == 'upload_mode':
        st.subheader("📝 오늘의 주식 기록하기")
    
        uploaded_file = st.file_uploader(
            "📸 MTS 캡처 화면 업로드",
            type=["png", "jpg", "jpeg"],
            key=f"uploader_{st.session_state['uploader_key']}"
        )
    
        if uploaded_file is not None:
            original_image = Image.open(uploaded_file).convert("RGB")
    
            st.markdown("### 🛡️ 민감 정보 가림막")
            mask_ratio = st.slider("가림막 높이 조절 (%)", min_value=0, max_value=40, value=20,
                                   help="보통 20% 정도면 계좌 잔고/번호 영역이 가려집니다.")
    
            image = original_image.copy()
            if mask_ratio > 0:
                draw = ImageDraw.Draw(image)
                width, height = image.size
                mask_height = int(height * (mask_ratio / 100.0))
                draw.rectangle(((0, 0), (width, mask_height)), fill="black")
    
            st.image(image, caption='최종 분석용 이미지', use_container_width=True)
    
            if st.button("✅ 가림막 설정 완료 및 정보 추출"):
                with st.spinner('이미지에서 종목과 수량을 읽어오고 있습니다...'):
                    # [변경 후]
                    config = types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema={
                            "type": "OBJECT",
                            "additionalProperties": {"type": "NUMBER"},
                        }
                    )
                    extract_prompt = (
                        "이 이미지는 MTS(모바일 트레이딩 앱) 잔고 화면입니다. "
                        "보유 중인 모든 종목명과 수량을 추출해줘. "
                        "숫자에 콤마(,)나 단위는 빼고 순수 숫자만 사용해."
                    )
    
                    text, err = safe_generate(
                        client=ai_client,
                        model_name=MODEL_NAME,
                        contents=[extract_prompt, image],
                        config=config,
                        fallback_msg="이미지 분석 중 오류가 발생했어요."
                    )
    
                    if err:
                        st.error(err)
                        st.info("잠시 후 다시 시도하거나, 아래의 '직접 입력'을 사용해주세요.")
                    else:
                        st.session_state['temp_extracted_data'] = text
                        st.session_state['processed_image'] = image
                        st.session_state['current_step'] = 'verify_data'
                        st.rerun()
    
        st.markdown("---")
        st.write("아이콘이 없는 종목은 직접 입력해주세요.")
    
        with st.form("manual_input_form", clear_on_submit=True):
            col_text, col_btn = st.columns([4, 1])
            with col_text:
                user_text_input = st.text_input("직접 입력", placeholder="예: 삼성전자 10주 매수 완료",
                                                label_visibility="collapsed")
            with col_btn:
                submitted = st.form_submit_button("추가")
    
            if submitted and user_text_input:
                st.session_state['daily_stock_list'].append(f"[직접 입력] {user_text_input}")
                st.success(f"'{user_text_input}' 내용이 추가되었습니다.")
                st.session_state['current_step'] = 'ask_next'
                st.rerun()
    
    # 2. 추출된 데이터 확인 및 수정 단계 (잔고 비교 → diff → 사유 입력)
    if st.session_state.get('current_step') == 'verify_data':
        st.subheader("🔍 변동 내역 확인 및 사유 입력")
    
        if 'processed_image' in st.session_state:
            st.image(st.session_state['processed_image'], caption='비교 확인용 사진', use_container_width=True)
    
        # ── 1) diff 계산 (폼 바깥에서 한 번만 실행) ──────────────────────
        try:
            ai_text = st.session_state.get('temp_extracted_data', '{}')
            # Structured Outputs 덕분에 순수 JSON이 보장됨 — 정규표현식 불필요
            extracted_dict = json.loads(ai_text.strip())
            extracted_dict = {k: float(v) for k, v in extracted_dict.items()}
        except Exception as e:
            st.error(f"AI 응답 파싱 실패 ({e}).")
            extracted_dict = {}
    
        current_inventory = {item["종목"]: item["수량"] for item in get_real_inventory(st.session_state["user_id"], supabase)}
    
        # AI가 인식한 종목에 대해서만 변동 추적
        # (사진에 없는 종목은 스크롤 미캡처 가능성이 있으므로 전량 매도로 간주하지 않음)
        diff_data = {}
        for stock, new_qty in extracted_dict.items():
            old_qty = float(current_inventory.get(stock, 0))
            change  = new_qty - old_qty
            if change != 0:
                diff_data[stock] = {"change": change, "old": old_qty, "new": new_qty}
    
        # ── 2) 폼 UI ──────────────────────────────────────────────────────
        if not diff_data:
            st.success("🎉 DB 잔고와 동일합니다. 새로 변동된 내역이 없습니다.")
        else:
            st.info(f"DB 잔고와 비교해 **{len(diff_data)}개 종목**에 변동이 감지됐습니다. 수량을 확인하고 매매 사유를 적어주세요.")
    
        with st.form(key='verify_diff_form'):
            if diff_data:
                for stock, info in diff_data.items():
                    change = info["change"]
                    badge = "🔴 매도" if change < 0 else "🟢 매수"
                    st.markdown(
                        f"**{stock}** &nbsp; {badge} &nbsp;"
                        f"<span style='color:gray;font-size:0.85em;'>"
                        f"{int(info['old'])}주 → {int(info['new'])}주</span>",
                        unsafe_allow_html=True
                    )
                    col_qty, col_memo = st.columns([1, 2])
                    with col_qty:
                        st.number_input(
                            "변동 수량 (+매수 / -매도)",
                            value=float(change),
                            key=f"qty_{stock}",
                            step=1.0
                        )
                    with col_memo:
                        st.text_input(
                            "매매 사유 (선택)",
                            placeholder="예: 배당금 재투자, 급락 추매",
                            key=f"memo_{stock}"
                        )
                    st.markdown("<hr style='margin:6px 0; border-color:#eee;'>", unsafe_allow_html=True)
    
            col_save, col_cancel = st.columns([7, 3])
            with col_save:
                submit_btn = st.form_submit_button(
                    "💾 확정 및 장바구니 담기",
                    type="primary",
                    disabled=not diff_data
                )
            with col_cancel:
                cancel_btn = st.form_submit_button("취소 및 다시 올리기")
    
            if submit_btn and diff_data:
                for stock in diff_data:
                    final_qty = st.session_state.get(f"qty_{stock}", 0)
                    memo      = st.session_state.get(f"memo_{stock}", "").strip()
                    if final_qty != 0:
                        action   = "매수" if final_qty > 0 else "매도"
                        memo_str = f" (사유: {memo})" if memo else ""
                        st.session_state['daily_stock_list'].append(
                            f"{stock} {abs(final_qty):.0f}주 {action}{memo_str}"
                        )
                st.session_state['current_step'] = 'ask_next'
                st.rerun()
    
            elif cancel_btn:
                st.session_state.pop('temp_extracted_data', None)
                st.session_state.pop('processed_image', None)
                st.session_state['uploader_key'] += 1
                st.session_state['current_step'] = 'upload_mode'
                st.rerun()
    
    # 3단계: 추가 입력 여부
    if st.session_state.get('current_step') == 'ask_next':
        st.markdown("### 💡 입력을 더 진행하시겠습니까?")
    
        with st.expander("현재까지 입력된 목록 확인", expanded=True):
            for i, item in enumerate(st.session_state['daily_stock_list']):
                col_text, col_del = st.columns([5, 1])
                with col_text:
                    st.write(f"- {item}")
                with col_del:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state['daily_stock_list'].pop(i)
                        st.rerun()
    
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 추가로 입력하기"):
                st.session_state['uploader_key'] += 1
                st.session_state['current_step'] = 'upload_mode'
                st.rerun()
        with col2:
            if st.button("📊 아니오, 이제 분석해주세요"):
                st.session_state['current_step'] = 'final_analysis'
                st.rerun()
    
    # 4단계: 최종 분석
    if st.session_state.get('current_step') == 'final_analysis':
        st.header("📝 오늘의 투자 종합 피드백")
    
        # [수정] 휘발성 위젯 대신 안전 금고에 저장된 멘토 데이터가 있는지 검사합니다.
        if not st.session_state.get('chosen_mentor'):
            st.warning("⚠️ AI 멘토가 지정되지 않았습니다!")
            st.info("💡 화면 상단의 '🤖 오늘의 멘토 설정' 창을 열어 오늘 대화할 멘토를 선택해주세요.")
            st.session_state['current_step'] = 'upload_mode'
            st.rerun()
    
        # [수정] 페르소나 매칭 로직도 금고 데이터(chosen_mentor) 기준으로 변경합니다.
        chosen_mentor = st.session_state['chosen_mentor']
    
        all_data_str = "\n".join(st.session_state['daily_stock_list'])
        show_balloons = has_tag(selected_tags, "#과거의나칭찬해") or has_tag(selected_tags, "#배당금달달해")
    
        if 'final_result' not in st.session_state and 'final_error' not in st.session_state:
            with st.spinner('오늘의 전체 투자 내역을 바탕으로 멘토가 분석 중입니다...'):
                base_instruction = """당신은 장기 투자자의 매매 일지 작성을 돕는 냉철하고 지혜로운 AI 페이스메이커입니다.
                사용자가 매매 메모(텍스트)와 함께 MTS 캡처 사진을 올릴 수 있습니다.
    
                [임무]
                1. 사진이 있다면: 데이터(종목, 수량, 수익률)를 정확히 추출하고, 확실치 않으면 사용자에게 되물어보세요.
                2. 감정은 무죄, 행동은 유죄: 사용자가 불안감(멘탈흔들림)을 표현하더라도 그 자체를 비난하지 마세요. 충동적인 행동(매도)을 막는 데 집중하세요.
                3. 패턴 인지: 제공된 [과거 기록]이 있다면, 이를 분석하여 사용자의 반복되는 실수 패턴이나 감정 패턴을 짚어내고 구체적인 행동(예: 24시간 HTS 삭제, 낮잠 등)을 처방하세요.
                """
    
                system_instruction = base_instruction
    
                past_records = get_past_context(selected_tags, supabase)
                if past_records:
                    system_instruction += past_records
    
                if has_tag(selected_tags, "#과거의나칭찬해") or has_tag(selected_tags, "#배당금달달해"):
                    system_instruction += "\n\n[현재 상태: 보상/칭찬] 땀 흘려 번 돈으로 우량 자산을 모아온 사용자의 인내심을 극찬해주세요! 축하와 함께 앞으로도 이 습관을 이어가도록 따뜻하게 격려해주세요."
                elif has_tag(selected_tags, "#오늘좀흔들"):
                    system_instruction += "\n\n[현재 상태: 불안] 감정은 무죄입니다! 흔들리는 감정을 공감해 주되, 과거 기록을 바탕으로 매도 버튼을 누르지 않도록 멘탈을 꽉 잡아주세요."
                elif has_tag(selected_tags, "#뇌동매매반성"):
                    system_instruction += "\n\n[현재 상태: 원칙 위반] 사용자가 충동 매매를 했습니다. 뼈 때리는 조언과 함께, 다음 하락장에서는 MTS 앱을 지워버리는 등의 강력한 시스템적 차단 규칙을 제안하세요."
                elif has_tag(selected_tags, "#존버는승리한다") or has_tag(selected_tags, "#오늘은안봤다") or has_tag(selected_tags, "#한템포쉬어가기"):
                    system_instruction += "\n\n[현재 상태: 능동적 회피 성공] 사용자가 시장을 의도적으로 멀리하거나 충동을 한 템포 늦추는 데 성공했습니다. 이것은 가장 어려운 형태의 자기 통제입니다. 작지만 진심으로 칭찬해주고, 이 패턴을 계속 유지하도록 격려하세요."
    
                if "심리 상담가" in chosen_mentor:
                    system_instruction += "\n\n[말투 지시] 사용자를 심리 상담 센터에 온 내담자처럼 대하세요. 매우 따뜻하고 부드러운 존댓말을 사용하며, 수익률의 등락보다는 사용자의 '감정 상태'와 '마음의 평화'를 어루만지는 데 집중하세요."
                elif "주식 찐친" in chosen_mentor:
                    system_instruction += "\n\n[말투 지시] 10년 지기 동네 친구처럼 100% 편안한 반말로 대답하세요. 장이 좋을 땐 오버하면서 같이 기뻐하고, 하락장일 땐 '야 나도 물렸어 버티자'는 식으로 친근하고 유쾌하게 위로해 주세요."
                elif "1타 강사" in chosen_mentor:
                    system_instruction += "\n\n[말투 지시] 수험생을 가르치는 깐깐한 일타 강사처럼 단호하고 팩트 위주의 말투를 사용하세요. 사용자가 감정에 휘둘릴 때는 매섭게 혼내고, 오직 '원칙 준수'와 '장기 투자'의 중요성만 차갑게 강조하세요."
    
                # ==========================================
                # 🧠 AI 시스템 프롬프트 (JSON 형식으로 강제 반환)
                # ==========================================
                system_instruction += f"""
                \n\n[출력 형식 지시]
                사용자의 일기 내용이나 매매 내역을 분석하여 아래의 '정확한 JSON 형식'으로만 답변해 주세요.
                절대 다른 마크다운이나 부연 설명을 덧붙이지 마세요.
    
                {{
                  "ai_feedback": "...",
                  "extracted_trades": [
                    {{
                      "stock_name": "삼성전자",
                      "quantity": 10,
                      "type": "buy" // 매수는 "buy", 매도는 "sell" 로 정확히 기재하세요.
                    }}
                  ]
                }}
    
                [ai_feedback 작성 규칙]
                - HTML 태그를 사용하세요. 줄바꿈은 <br><br>, 강조는 <b>텍스트</b>.
                - 반드시 아래 3단 구조로 작성하세요:
                  1) 따뜻한 공감 인사 (오늘 하루 수고를 알아주는 2~3문장)
                  2) 투자 내역에 대한 진심 어린 감상과 격려 (2~3문장, 구체적 종목/행동을 언급)
                  3) <b>[오늘의 처방]</b> 로 시작하는 구체적인 행동 처방 1가지 (짧고 실천 가능하게)
                - 마치 옆에 앉아 말하듯 사용자를 '투자자님'으로 부르세요.
                - 숫자나 종목명을 언급할 때도 차갑게 나열하지 말고 감정과 함께 녹여내세요.
    
                * 주의사항 1: 매수/매도 기록이 없다면 "extracted_trades"는 빈 배열 [] 로 두세요.
                * 주의사항 2: 사용자가 주식 종목명, 수량을 입력했거나 이미지에 있다면 반드시 추출하세요. 가격은 추출하지 않아도 됩니다.
                * 주의사항 3: extracted_trades의 각 항목에는 stock_name과 quantity만 포함하면 됩니다.
                """
    
                # [변경 후]
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
    
                tag_text = " ".join(selected_tags) if selected_tags else ""
                final_prompt = f"태그: {tag_text}\n\n사용자가 오늘 다음 종목들을 매수/확인했습니다:\n{all_data_str}\n\n이 내역을 바탕으로 전체적인 투자 평과 멘탈 관리 조언을 해줘."
    
                final_text, err = safe_generate(
                    client=ai_client,
                    model_name=MODEL_NAME,
                    contents=final_prompt,
                    config=config,
                    fallback_msg="최종 피드백 생성 중 오류가 발생했어요."
                )
    
                if err:
                    st.session_state['final_error'] = err
                else:
                    try:
                        # response_mime_type="application/json" 덕분에 순수 JSON이 보장됨
                        ai_data = json.loads(final_text.strip())
                        
                        ai_feedback = ai_data.get("ai_feedback", "기록이 저장되었습니다.")
                        extracted_trades = ai_data.get("extracted_trades", [])
    
                        st.session_state['final_result'] = ai_feedback
    
                        # ==========================================
                        # 📦 DB 저장 준비: 가격 일괄 조회
                        # ==========================================
                        trades_to_insert = []
                        if extracted_trades:
                            # 1) 정규화 + 티커 매핑
                            tickers_to_fetch = []
                            for trade in extracted_trades:
                                raw_name   = trade["stock_name"]
                                normalized = " ".join(raw_name.split())
                                ticker     = TICKER_MAP.get(normalized) or TICKER_MAP.get(raw_name)
                                trade["_normalized_name"] = normalized
                                trade["_ticker"]          = ticker
                                if ticker:
                                    tickers_to_fetch.append(ticker)
    
                            # 2) 한 번에 가격 조회
                            bulk_trade_prices = get_realtime_prices_bulk(tuple(tickers_to_fetch), time_bucket=_market_time_bucket()) if tickers_to_fetch else {}
    
                            # 3) 저장 목록 조립
                            for trade in extracted_trades:
                                ticker = trade["_ticker"]
                                if ticker:
                                    real_price = bulk_trade_prices.get(ticker) or 0.0
                                    currency   = "KRW" if ticker.endswith(".KS") else "USD"
                                else:
                                    real_price = 0.0
                                    currency   = "KRW"
                                
                                trades_to_insert.append({
                                    "stock_name": trade["_normalized_name"],
                                    "quantity":   abs(trade["quantity"]), # 수량은 무조건 절대값으로 DB 저장
                                    "price":      real_price,
                                    "currency":   currency,
                                    "type":       trade.get("type", "buy") # AI가 판별한 buy 또는 sell 저장
                                })
    
                        # ==========================================
                        # 📦 DB 실제 저장
                        # ==========================================
                        tags_str = ", ".join(selected_tags) if selected_tags else ""
                        _uid = st.session_state["user_id"]
                        supabase.table("journals").insert({
                            "user_id":     _uid,
                            "tags":        tags_str,
                            "content":     all_data_str,
                            "ai_feedback": ai_feedback,
                        }).execute()
                        get_recent_journals.clear()
    
                        if trades_to_insert:
                            for t in trades_to_insert:
                                t["user_id"] = _uid
                            supabase.table("trades").insert(trades_to_insert).execute()
                        get_real_inventory.clear()
                                
                    except json.JSONDecodeError as e:
                        st.session_state['final_error'] = f"JSON 파싱 실패: {e}\n\n원본 응답:\n{final_text}"
                    except Exception as e:
                        st.error(f"⚠️ 저장 중 오류: {e}")
                        st.session_state['final_error'] = f"저장 실패: {e}"
    
        if 'final_error' in st.session_state:
            st.error(st.session_state['final_error'])
            st.info("위 오류가 일시적인 것 같으면 잠시 후 다시 시도해주세요. **입력하신 내역은 아직 저장되지 않았습니다.**")
        elif 'final_result' in st.session_state:
            if show_balloons and not st.session_state.get('balloons_shown'):
                st.balloons()
                st.session_state['balloons_shown'] = True
            if not st.session_state.get('toast_shown'):
                st.toast("일기와 매매 기록이 창고에 입고되었습니다!", icon="📦")
                st.session_state['toast_shown'] = True
            st.markdown(st.session_state['final_result'], unsafe_allow_html=True)
    
        if st.button("🔄 처음으로 돌아가기"):
            st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
            for key in ['daily_stock_list', 'current_step', 'temp_extracted_data', 'balloons_shown',
                        'toast_shown', 'processed_image', 'current_tags', 'chat_messages',
                        'final_result', 'final_error']:
                st.session_state.pop(key, None)
            st.rerun()
    
    # ==========================================
    # 📊 [이동됨] 나의 투자 능력치 (tab1 최하단 - 단계와 무관하게 항상 표시)
    # ==========================================
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("#### 📊 나의 투자 능력치 종합")
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em;'>최근 30일 동안의 기록 패턴을 분석한 결과입니다.</p>", unsafe_allow_html=True)
    
    if zen_mode:
        banner("🌿 <b>동굴 모드 작동 중</b><br>현재 점수와 투자 능력치 차트가 가려져 있습니다. 천천히 흔들리지 않는 마음이 가장 든든한 무기입니다.", type="success")
    else:
        current_scores = calculate_scores(supabase)
        
        # 레이아웃을 카드로 깔끔하게 감싸기
        radar_fig = render_radar_chart(current_scores)
        st.plotly_chart(radar_fig, use_container_width=True)
        
        streak_days = int(current_scores['성실도'] // 3.3)
        banner(f"🔥 현재 <b>{streak_days}일 연속</b> 기록 중입니다! 멋진 페이스를 보여주고 계시네요.", type="info")
    
    # ---------------------------------------------------------
    # 탭 2: 과거 기록 조회