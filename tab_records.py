import streamlit as st
import html
import datetime
from db import to_kst_str, get_recent_journals, calculate_investment_score, delete_journal, get_real_inventory
from ui_components import card, banner, sanitize_html
from prices import get_usd_to_krw, _market_time_bucket

def render_records_tab(supabase):
    user_id = st.session_state.get("user_id")
    if not user_id:
        banner("로그인이 필요합니다.", type="warning")
        return

    st.markdown("### 📊 나의 자산 성장 기록")
    
    # 1. 배당 시계 (가장 직관적인 숫자)
    render_dividend_clock(supabase, user_id)
    
    # 2. 복리 시뮬레이터 (미래 기대감)
    render_future_simulator(supabase, user_id)
    
    # 3. 과거 멘탈 회고 (성장 서사)
    render_past_reflection(supabase, user_id)

    st.markdown("---")

    # ── 최근 30일 나의 투자 성과 브리핑 ────────────────────
    if user_id:
        with st.expander("📊 나의 투자 점수 브리핑", expanded=False):
            st.markdown(
                "<p style='color:#8B95A1; font-size:0.88em;'>"
                "보유 종목의 품질, 장기 보유 기간, 투자 습관을 종합해 점수를 냅니다."
                "</p>",
                unsafe_allow_html=True,
            )
            try:
                sc = calculate_investment_score(supabase, user_id)
            except Exception as e:
                st.warning(f"점수 계산 실패: {e}")
                sc = None

            if sc:
                total   = sc["total"]
                grade   = sc["grade"]
                gemoji  = sc["grade_emoji"]
                cats    = sc["categories"]
                evals   = sc["stock_evals"]
                habit   = sc["habit_detail"]

                # ── 총점 헤더 ──────────────────────────────
                st.markdown(
                    f"""
                    <div style="text-align:center; padding:20px 0 12px 0;">
                      <div style="font-size:3rem; line-height:1;">{gemoji}</div>
                      <div style="font-size:2.6rem; font-weight:800; color:#191F28; line-height:1.1;">{total}<span style="font-size:1.2rem; color:#8B95A1; font-weight:500;">점</span></div>
                      <div style="font-size:1.1rem; font-weight:700; color:#3182F6; margin-top:4px;">{grade}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # ── 카테고리별 점수 바 ──────────────────────
                st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

                cat_colors = {
                    "종목 품질": "#3182F6",
                    "장기 보유": "#00B85C",
                    "투자 습관": "#F5A623",
                }
                cat_icons = {
                    "종목 품질": "💎",
                    "장기 보유": "⏳",
                    "투자 습관": "🏃",
                }
                for cat_name, cat_data in cats.items():
                    s = cat_data["score"]
                    m = cat_data["max"]
                    pct = int(s / m * 100)
                    color = cat_colors.get(cat_name, "#3182F6")
                    icon  = cat_icons.get(cat_name, "")
                    st.markdown(
                        f"""
                        <div style="margin-bottom:12px;">
                          <div style="display:flex; justify-content:space-between; font-size:0.88em; font-weight:600; color:#333D4B; margin-bottom:4px;">
                            <span>{icon} {cat_name}</span>
                            <span style="color:{color};">{s} / {m}점</span>
                          </div>
                          <div style="background:#F2F4F6; border-radius:8px; height:10px; overflow:hidden;">
                            <div style="width:{pct}%; background:{color}; height:100%; border-radius:8px; transition:width 0.4s;"></div>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # ── 등급 안내 ──────────────────────────────
                st.markdown(
                    """
                    <div style="background:#F9FAFB; border-radius:10px; padding:10px 14px; margin:8px 0 12px 0; font-size:0.8em; color:#6B7684;">
                    🏆 90점+ 전설의 투자자 &nbsp;|&nbsp;
                    💎 75점+ 장기투자 고수 &nbsp;|&nbsp;
                    📈 60점+ 성장하는 투자자 &nbsp;|&nbsp;
                    🌱 45점+ 기초 다지는 중 &nbsp;|&nbsp;
                    🐣 ~44점 투자 입문 단계
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # ── 종목별 상세 ────────────────────────────
                if evals:
                    with st.expander("종목별 점수 상세 보기", expanded=False):
                        # 습관 점수 상세
                        col_h1, col_h2, col_h3 = st.columns(3)
                        col_h1.metric("정기 매수 횟수", f"{habit['routine']}회", f"+{habit['routine']*5}점")
                        col_h2.metric("멘탈 방어 횟수", f"{habit['defense']}회", f"+{habit['defense']*3}점")
                        col_h3.metric("뇌동매매 횟수", f"{habit['panic']}회",
                                      f"-{habit['panic']*5}점" if habit['panic'] else "0점",
                                      delta_color="inverse" if habit['panic'] else "off")

                        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

                        # 종목 테이블
                        for ev in evals:
                            hold_str = (
                                f"{ev['hold_days']}일 보유" if ev["hold_days"] > 0 else "기록 없음"
                            )
                            st.markdown(
                                f"""
                                <div style="display:flex; justify-content:space-between; align-items:center;
                                            padding:8px 12px; background:#F9FAFB; border-radius:8px; margin-bottom:6px;
                                            font-size:0.85em;">
                                  <div>
                                    <span style="font-weight:700; color:#191F28;">{ev['name']}</span>
                                    <span style="color:#8B95A1; margin-left:8px;">{ev['ticker']}</span>
                                    <span style="background:#E8F4FF; color:#3182F6; border-radius:4px;
                                                 padding:1px 6px; font-size:0.78em; margin-left:8px;">{ev['type']}</span>
                                  </div>
                                  <div style="text-align:right; white-space:nowrap;">
                                    <span style="color:#6B7684; margin-right:12px;">{hold_str}</span>
                                    <span style="font-weight:700; color:#3182F6;">품질 +{ev['quality_pts']}점</span>
                                    <span style="font-weight:700; color:#00B85C; margin-left:8px;">보유 +{ev['hold_pts']}점</span>
                                  </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                # ── 점수 올리는 방법 힌트 ─────────────────
                hints = []
                if cats["종목 품질"]["score"] < 30:
                    hints.append("💡 ETF나 우량주 비중을 늘리면 **종목 품질** 점수가 오릅니다.")
                if cats["장기 보유"]["score"] < 25:
                    hints.append("💡 보유 기간이 길어질수록 **장기 보유** 점수가 자동으로 올라갑니다. 존버가 정답!")
                if habit["routine"] == 0:
                    hints.append("💡 정기 매수를 실천하고 **#월급날정기매수** 태그를 남기면 습관 점수를 받을 수 있어요.")
                if hints:
                    st.markdown(
                        "<div style='margin-top:8px; padding:10px 14px; background:#FFF8E1; border-radius:10px; font-size:0.84em; color:#555;'>"
                        + "<br>".join(hints)
                        + "</div>",
                        unsafe_allow_html=True,
                    )


    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)
    if not user_id:
        banner("로그인이 필요합니다.", type="warning")
        return

    rows = get_recent_journals(user_id, supabase)

    if not rows:
        banner("아직 작성된 일기가 없어요. 첫 일기를 작성해보세요! ✍️", type="info")
    else:
        st.markdown(f"<div style='font-size: 0.85em; color: #8B95A1; font-weight: 500; margin-bottom: 12px;'>총 {len(rows)}개의 발자국</div>", unsafe_allow_html=True)

        all_tags_in_db = set()
        for r in rows:
            if r.get("tags"):
                for t in r["tags"].split(", "):
                    if t.strip():
                        all_tags_in_db.add(t.strip())

        filter_tag = None
        if all_tags_in_db:
            # 아름다운 태그 필터 드롭다운
            filter_tag = st.selectbox(
                "🎯 관심 있는 태그별로 모아보기",
                options=["🔍 전체 일기 보기"] + sorted(all_tags_in_db),
                index=0
            )
            if filter_tag == "🔍 전체 일기 보기":
                filter_tag = None

        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

        for r in rows:
            created_at = to_kst_str(r["created_at"])
            tags_in_row = r.get("tags") or ""
            content = r.get("content") or ""
            feedback = r.get("ai_feedback") or ""
            journal_id = r.get("id")

            if filter_tag and filter_tag not in tags_in_row:
                continue

            # 태그를 예쁜 뱃지들로 시각화
            badges_html = ""
            if tags_in_row:
                for tag in tags_in_row.split(", "):
                    if tag:
                        badges_html += f"<span style='background: #E8F4FF; color: #3182F6; padding: 3px 8px; border-radius: 6px; font-size: 0.8em; font-weight: 600; margin-right: 6px;'>{html.escape(tag)}</span>"
            else:
                badges_html = "<span style='color: #ADB5BD; font-size: 0.8em;'>태그 없음</span>"

            # KST 변환된 날짜 포맷 정리 (초 제외 YYYY-MM-DD HH:MM)
            date_display = created_at[:-3] if len(created_at) > 16 else created_at

            expander_title = f"📅 {date_display}"

            with st.expander(expander_title):
                st.markdown(f"<div style='margin-bottom: 12px;'>{badges_html}</div>", unsafe_allow_html=True)

                # 오늘의 매수 내역 카드
                safe_content = html.escape(content)
                purchase_html = f"""
                <div style="background: #F9FAFB; padding: 14px; border-radius: 10px; border-left: 3px solid #6B7684; margin-bottom: 14px; white-space: pre-wrap; font-family: Pretendard; font-size: 0.92em; color: #333D4B;">
{safe_content}
                </div>
                """
                st.markdown("**🛒 오늘의 매매 내역**")
                st.markdown(purchase_html, unsafe_allow_html=True)

                # AI 피드백
                st.markdown("**🧠 AI 멘토의 솔루션**")
                # [수정 #2] AI 생성 HTML을 sanitize 처리하여 XSS 방어
                feedback_html = f"""
                <div style="background: #E8F4FF; padding: 14px; border-radius: 10px; border-left: 3px solid #3182F6; font-family: Pretendard; font-size: 0.92em; color: #191F28; line-height: 1.6;">
{sanitize_html(feedback)}
                </div>
                """
                st.markdown(feedback_html, unsafe_allow_html=True)

                # ── 삭제 버튼 ────────────────────────────────────
                st.markdown("<div style='margin-top:16px; border-top:1px solid #F0F0F0; padding-top:12px;'></div>", unsafe_allow_html=True)

                pending = st.session_state.get("pending_delete_id")

                if pending == journal_id:
                    # 삭제 확인 단계
                    st.warning("⚠️ 이 일기를 삭제하면 **되돌릴 수 없어요.** 정말 삭제할까요?")
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button("네, 삭제할게요", key=f"confirm_del_{journal_id}", type="primary", use_container_width=True):
                            try:
                                delete_journal(journal_id, user_id, supabase)
                                st.session_state.pop("pending_delete_id", None)
                                st.toast("일기가 삭제됐어요.", icon="🗑️")
                                st.rerun()
                            except Exception as e:
                                st.error(f"삭제 실패: {e}")
                    with col_cancel:
                        if st.button("취소", key=f"cancel_del_{journal_id}", use_container_width=True):
                            st.session_state.pop("pending_delete_id", None)
                            st.rerun()
                else:
                    # 삭제 버튼 (우측 정렬)
                    _, col_del = st.columns([6, 1])
                    with col_del:
                        if st.button("삭제", key=f"del_btn_{journal_id}", help="이 일기 삭제", use_container_width=True):
                            st.session_state["pending_delete_id"] = journal_id
                            st.rerun()


def render_dividend_clock(supabase, user_id: str):
    """배당 시계: 누적 투자금액 대비 시간당 수익 계산"""
    inventory = get_real_inventory(user_id, supabase)
    if not inventory:
        return
        
    total_invested_krw = 0
    usd_krw = get_usd_to_krw(_market_time_bucket())
    for item in inventory:
        val = item["수량"] * item["평단가"]
        if item["통화"] == "USD":
            val *= usd_krw # 실시간 환율 적용
        total_invested_krw += val

    annual_dividend = total_invested_krw * 0.03 # 예상 연 배당률 3%
    hourly_wage = annual_dividend / (365 * 24)
    
    if hourly_wage > 0:
        content = f"""
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 4px 0;">
            <div>
                <div style="font-size: 0.95rem; color: #4E5968;">내 자본의 시급은?</div>
                <div style="font-size: 1.8rem; font-weight: 800; color: #3182F6; margin-top: 4px;">
                    시간당 {hourly_wage:,.0f}원 ⏰
                </div>
            </div>
        </div>
        <div style="font-size: 0.85rem; color: #8B95A1; margin-top: 12px; background: #F2F4F6; padding: 8px 12px; border-radius: 8px;">
            ※ 현재 투자 원금 기준 (예상 연 배당률 3% 복리 제외)
        </div>
        """
        card(title="", content_html=content)


def render_future_simulator(supabase, user_id: str):
    """N년 후 배당 시뮬레이터"""
    inventory = get_real_inventory(user_id, supabase)
    current_principal = 0
    usd_krw = get_usd_to_krw(_market_time_bucket())
    if inventory:
        for item in inventory:
            val = item["수량"] * item["평단가"]
            if item["통화"] == "USD": 
                val *= usd_krw
            current_principal += val

    with st.expander("🔮 복리의 마법: 미래 내 배당금은 얼마일까?"):
        col1, col2 = st.columns(2)
        with col1:
            monthly_add = st.number_input("월 적립액 (만원)", min_value=0, value=50, step=10)
        with col2:
            years = st.slider("투자 기간 (년)", min_value=1, max_value=30, value=10)
            
        annual_growth_rate = 0.07 # 연평균 성장 7%
        dividend_yield = 0.03     # 배당률 3%
        
        # 복리 계산식
        future_val_principal = current_principal * ((1 + annual_growth_rate) ** years)
        monthly_add_krw = monthly_add * 10000
        months = years * 12
        monthly_rate = annual_growth_rate / 12
        
        if monthly_rate > 0:
            future_val_monthly = monthly_add_krw * (((1 + monthly_rate) ** months - 1) / monthly_rate) * (1 + monthly_rate)
        else:
            future_val_monthly = monthly_add_krw * months
            
        total_future_asset = future_val_principal + future_val_monthly
        expected_monthly_dividend = (total_future_asset * dividend_yield) / 12
        
        content = f"""
        <div style="text-align: center; padding: 12px 0;">
            <div style="font-size: 1rem; color: #4E5968; margin-bottom: 8px;">{years}년 뒤 매월 받을 배당금</div>
            <div style="font-size: 2.2rem; font-weight: 800; color: #3182F6;">{expected_monthly_dividend/10000:,.0f}만 원 💸</div>
            <hr style="border: 0; border-top: 1px dashed #E5E8EB; margin: 20px 0;">
            <div style="font-size: 0.95rem; color: #4E5968;">예상 총 자산: <b>{total_future_asset/100000000:,.1f}억 원</b></div>
            <div style="font-size: 0.8rem; color: #8B95A1; margin-top: 8px;">※ 연 성장 7%, 배당 3% 가정</div>
        </div>
        """
        card(title="", content_html=content)


def render_past_reflection(supabase, user_id: str):
    """과거의 나와 비교 (AI 성장 서사)"""
    # 30일 이전의 흔들렸던 감정 기록 탐색
    thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
    
    try:
        resp = (
            supabase.table("journals")
            .select("created_at, content")
            .eq("user_id", user_id)
            .lte("created_at", thirty_days_ago)
            .or_("tags.ilike.%#뇌동매매반성%,tags.ilike.%#오늘좀흔들%,tags.ilike.%#오늘의실수%")
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        past_journal = resp.data[0] if resp.data else None
    except Exception:
        past_journal = None

    if past_journal:
        past_date = to_kst_str(past_journal["created_at"]).split()[0]
        # XSS 방어를 위해 사용자 작성 내용은 반드시 이스케이프 처리
        safe_content = html.escape(past_journal["content"])
        
        content = f"""
        <div style="background: #F0F4FF; padding: 16px; border-radius: 12px; margin-bottom: 16px;">
            <div style="font-size: 0.85rem; color: #3182F6; font-weight: 700; margin-bottom: 8px;">
                📅 {past_date}의 일기
            </div>
            <div style="font-size: 0.95rem; color: #4E5968; font-style: italic; line-height: 1.5;">
                "{safe_content}"
            </div>
        </div>
        <div style="font-size: 0.95rem; color: #191F28; line-height: 1.6;">
            과거에는 불안함에 흔들렸지만, 지금 당신의 자산은 굳건하게 성장 중입니다. <b>위기를 넘기고 투자를 지속한 스스로를 칭찬해주세요!</b> 👏
        </div>
        """
        card(title="🕰️ AI가 찾아낸 과거의 기록", content_html=content, icon="🌱")
