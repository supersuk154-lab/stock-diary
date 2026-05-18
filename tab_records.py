import streamlit as st
import html
from db import to_kst_str, get_recent_journals
from ui_components import card, banner, sanitize_html

def render_records_tab(supabase):
    st.markdown("### 📚 나의 투자 기록장")
    st.markdown("<p style='color: #4E5968; font-size: 0.95em;'>과거에 기록한 일기와 AI 멘토의 피드백을 모아볼 수 있습니다.</p>", unsafe_allow_html=True)

    user_id = st.session_state.get("user_id")
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

            if filter_tag and filter_tag not in tags_in_row:
                continue

            # 태그를 예쁜 뱃지들로 시각화
            badges_html = ""
            if tags_in_row:
                for tag in tags_in_row.split(", "):
                    if tag:
                        badges_html += f"<span style='background: #E8F4FF; color: #3182F6; padding: 3px 8px; border-radius: 6px; font-size: 0.8em; font-weight: 600; margin-right: 6px;'>{tag}</span>"
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
