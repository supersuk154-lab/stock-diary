import streamlit as st
from prices import get_market_weather, _market_time_bucket
from ui_components import banner
from diary_inventory import render_inventory_section
from diary_chat import render_chat_section
from diary_upload import render_upload_section


def render_diary_tab(supabase, ai_client, dev_mode):
    """일기 작성 탭: 날씨 티커 → 태그/채팅 → 업로드 → 보물함 순서."""

    def sync_mentor():
        mentor = st.session_state.get("persona_widget")
        if mentor:
            st.session_state["chosen_mentor"] = mentor
            try:
                supabase.auth.update_user({"data": {"chosen_mentor": mentor}})
            except Exception:
                pass

    # ── 사이드바: 멘토 선택 ──────────────────
    zen_mode = st.session_state.get("zen_mode", False)

    st.sidebar.markdown("**🤖 오늘의 멘토**")

    _mentor_options = [
        "🤖 정중한 AI 비서 (기본/깔끔)",
        "☕ 따뜻한 심리 상담가 (공감/위로)",
        "🤝 다정한 주식 찐친 (유쾌한 반말)",
        "🧊 팩트폭행 1타 강사 (단호/원칙)",
    ]
    if zen_mode:
        _mentor_options = [
            "☕ 따뜻한 심리 상담가 (공감/위로)",
            "🤖 정중한 AI 비서 (기본/깔끔)",
            "🤝 다정한 주식 찐친 (유쾌한 반말)",
            "🧊 팩트폭행 1타 강사 (단호/원칙)",
        ]

    _saved = st.session_state.get("chosen_mentor")
    _default_idx = _mentor_options.index(_saved) if _saved in _mentor_options else None

    st.sidebar.selectbox(
        "멘토 선택",
        options=_mentor_options,
        index=_default_idx,
        placeholder="멘토를 선택하세요",
        key="persona_widget",
        on_change=sync_mentor,
        label_visibility="collapsed",
    )
    if not st.session_state.get("chosen_mentor"):
        st.sidebar.caption("⚠️ 멘토 선택 후 AI 대화가 가능합니다.")

    # ── 증시 날씨: 1줄 티커 + 접힘 상세 ─────────────────
    if not zen_mode:
        _weather = get_market_weather(time_bucket=_market_time_bucket())
        _ticker_parts = []
        for _name, _data in _weather.items():
            if _data:
                _pct = _data["change_pct"]
                _arrow = "▲" if _pct > 0 else ("▼" if _pct < 0 else "–")
                _c = "#e03131" if _pct > 0 else ("#1c7ed6" if _pct < 0 else "#868e96")
                _ticker_parts.append(
                    f'<span style="margin-right:16px; font-size:0.85em; font-weight:600; white-space:nowrap;">'
                    f'{_name} <span style="color:{_c};">{_arrow}{abs(_pct):.2f}%</span></span>'
                )

        if _ticker_parts:
            st.markdown(
                '<div style="background:#F8F9FA; border-radius:10px; padding:10px 16px; '
                'margin-bottom:8px; overflow-x:auto; white-space:nowrap;">'
                + "".join(_ticker_parts)
                + "</div>",
                unsafe_allow_html=True,
            )

        with st.expander("📊 증시 날씨 자세히 보기", expanded=False):
            _items = list(_weather.items())
            for _row in (_items[:2], _items[2:]):
                _cols = st.columns(2)
                for _col, (_n, _d) in zip(_cols, _row):
                    with _col:
                        if _d:
                            _pct = _d["change_pct"]
                            _curr = _d["current"]
                            _color, _icon, _arrow = (
                                ("#e03131", "☀️", "▲") if _pct > 0
                                else ("#1c7ed6", "☔", "▼") if _pct < 0
                                else ("#868e96", "☁️", "–")
                            )
                            st.markdown(
                                f'<div style="background:#f8f9fa; border-radius:12px; padding:16px; '
                                f'text-align:center; border:1px solid #e9ecef; margin-bottom:8px;">'
                                f'<div style="font-size:0.82em; color:#495057; font-weight:600;">{_n} {_icon}</div>'
                                f'<div style="font-size:1.3em; font-weight:800; margin:6px 0;">{_curr:,.2f}</div>'
                                f'<div style="font-size:0.9em; font-weight:700; color:{_color};">'
                                f'{_arrow} {abs(_pct):.2f}%</div></div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f'<div style="background:#f8f9fa; border-radius:12px; padding:16px; '
                                f'text-align:center; border:1px solid #e9ecef; margin-bottom:8px;">'
                                f'<div style="font-size:0.82em; color:#495057; font-weight:600;">{_n}</div>'
                                f'<div style="font-size:0.85em; color:#adb5bd; margin-top:12px;">💤 수신 지연</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
    
    # ── 동굴 모드 토글 (증시 날씨 자세히 보기 하단 배치) ─────────
    with st.container(border=True):
        col_text, col_toggle = st.columns([4, 1])
        with col_text:
            st.markdown(
                "<span style='font-weight:700; font-size:0.95em; color:#333D4B;'>🦇 동굴 대피 모드</span><br>"
                "<span style='font-size:0.8em; color:#8B95A1; line-height:1.3;'>시장이 폭락해 흔들릴 때 켜세요. 모든 자산 금액과 수익률을 숨겨줍니다.</span>",
                unsafe_allow_html=True
            )
        with col_toggle:
            zen_mode = st.toggle(
                "동굴 모드",
                value=st.session_state.get("zen_mode", False),
                key="zen_mode",
                label_visibility="collapsed"
            )

    st.markdown("<div style='margin:20px 0'></div>", unsafe_allow_html=True)

    # ── 1. 태그 선택 + AI 멘토 대화 ──────────────────────
    selected_tags = render_chat_section(supabase, ai_client)

    st.markdown("<div style='margin:28px 0'></div>", unsafe_allow_html=True)

    # ── 2. 매매 및 이미지 기록 업로드 ────────────────────
    render_upload_section(supabase, ai_client, selected_tags)

    st.markdown("<div style='margin:28px 0'></div>", unsafe_allow_html=True)

    # ── 3. 나의 보물함 (실시간 주가 연동) ────────────────
    render_inventory_section(supabase, st.session_state["user_id"], zen_mode, ai_client)
