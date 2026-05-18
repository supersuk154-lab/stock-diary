import streamlit as st
from prices import get_market_weather, _market_time_bucket
from db import calculate_scores
from ui_components import render_radar_chart, banner
from diary_inventory import render_inventory_section
from diary_chat import render_chat_section
from diary_upload import render_upload_section

def render_diary_tab(supabase, ai_client, dev_mode):
    """일기 작성 탭을 구성하며 보물함, 멘토 대화, 이미지 업로드, 그리고 능력치 컴포넌트를 조립합니다."""
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
        
        saved_mentor = st.session_state.get("chosen_mentor")
        default_index = options.index(saved_mentor) if saved_mentor in options else None
    
        st.selectbox(
            "오늘의 멘토를 선택하세요",
            options=options,
            index=default_index,
            placeholder="⚠️ 멘토가 설정되지 않았습니다 (터치해서 선택)",
            key="persona_widget",
            on_change=sync_mentor,
            label_visibility="collapsed"
        )
        
    if st.session_state.get("chosen_mentor"):
        st.success(f"✅ **{st.session_state['chosen_mentor']}**(으)로 설정되었습니다. 든든한 조언을 기대해주세요!")
    else:
        st.warning("⚠️ **멘토가 설정되지 않았습니다.** 위 '🤖 오늘의 멘토 설정' 창을 터치하여 오늘 대화할 멘토를 골라주세요.")
    
    st.markdown("---")

    # ---------------------------------------------------------
    # 📦 2. 나의 보물함 (Inventory) - 실시간 주가 연동
    # ---------------------------------------------------------
    render_inventory_section(supabase, st.session_state["user_id"], zen_mode)

    st.markdown("---")

    # ---------------------------------------------------------
    # 💬 3. 오늘의 상태 태그 선택 및 AI 멘토 대화
    # ---------------------------------------------------------
    selected_tags = render_chat_section(supabase, ai_client)

    st.markdown("---")

    # ---------------------------------------------------------
    # 📝 4. 매매 및 이미지 기록 업로드 섹션
    # ---------------------------------------------------------
    render_upload_section(supabase, ai_client, selected_tags)

    # ==========================================
    # 📊 5. 나의 투자 능력치 종합 (항상 표시)
    # ==========================================
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("#### 📊 나의 투자 능력치 종합")
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em;'>최근 30일 동안의 기록 패턴을 분석한 결과입니다.</p>", unsafe_allow_html=True)
    
    if zen_mode:
        banner("🌿 <b>동굴 모드 작동 중</b><br>현재 점수와 투자 능력치 차트가 가려져 있습니다. 천천히 흔들리지 않는 마음이 가장 든든한 무기입니다.", type="success")
    else:
        # [수정] calculate_scores에 st.session_state["user_id"] 를 추가적으로 넘겨주어 보안 패치 반영
        current_scores = calculate_scores(supabase, st.session_state.get("user_id", ""))
        
        radar_fig = render_radar_chart(current_scores)
        st.plotly_chart(radar_fig, use_container_width=True)
        
        streak_days = int(current_scores['성실도'] // 3.3)
        banner(f"🔥 현재 <b>{streak_days}일 연속</b> 기록 중입니다! 멋진 페이스를 보여주고 계시네요.", type="info")