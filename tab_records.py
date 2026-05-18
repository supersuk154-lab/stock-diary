import streamlit as st
from db import to_kst_str, get_recent_journals

def render_records_tab(supabase):
    st.header("📚 나의 투자 기록장")

    # [변경] user_id를 캐시 키로 전달
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("로그인이 필요합니다.")
        return

    rows = get_recent_journals(user_id, supabase)

    if not rows:
        st.info("아직 작성된 일기가 없어요. 첫 일기를 작성해보세요!")
    else:
        st.caption(f"최근 일기 {len(rows)}개")

        all_tags_in_db = set()
        for r in rows:
            if r.get("tags"):
                for t in r["tags"].split(", "):
                    if t.strip():
                        all_tags_in_db.add(t.strip())

        filter_tag = None
        if all_tags_in_db:
            filter_tag = st.selectbox(
                "태그로 필터링",
                options=["(전체 보기)"] + sorted(all_tags_in_db),
                index=0
            )
            if filter_tag == "(전체 보기)":
                filter_tag = None

        for r in rows:
            id_ = r["id"]
            created_at = to_kst_str(r["created_at"])  # [변경] KST 변환
            tags_in_row = r.get("tags") or ""
            content = r.get("content") or ""
            feedback = r.get("ai_feedback") or ""

            if filter_tag and filter_tag not in tags_in_row:
                continue

            label_tags = tags_in_row if tags_in_row else "(태그 없음)"
            with st.expander(f"📅 {created_at}  ·  {label_tags}"):
                st.markdown("**🛒 오늘의 매수 내역**")
                st.text(content)
                st.markdown("**🧠 AI 멘토의 피드백**")
                st.markdown(feedback, unsafe_allow_html=True)
