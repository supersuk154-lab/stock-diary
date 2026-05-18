import streamlit as st
import json
import datetime
from db import to_kst_str, KST, get_recent_journals, get_real_inventory

def render_settings_tab(supabase):
    st.header("⚙️ 설정 및 데이터 관리")

    # 비밀번호 변경 (로그인 상태)
    st.markdown("### 🔑 비밀번호 변경")
    with st.form("change_pw_form", clear_on_submit=True):
        cp_new = st.text_input("새 비밀번호", type="password", placeholder="6자리 이상")
        cp_new2 = st.text_input("새 비밀번호 확인", type="password")
        cp_btn = st.form_submit_button("🔒 변경하기", type="primary")
    if cp_btn:
        if not cp_new or not cp_new2:
            st.warning("모든 항목을 입력해주세요.")
        elif cp_new != cp_new2:
            st.error("❌ 비밀번호가 일치하지 않습니다.")
        elif len(cp_new) < 6:
            st.warning("6자리 이상으로 설정해주세요.")
        else:
            try:
                supabase.auth.update_user({"password": cp_new})
                st.success("✅ 비밀번호가 변경되었습니다.")
            except Exception as e:
                st.error(f"변경 실패: {e}")

    st.markdown("---")

    st.markdown("### 💾 내 일기 데이터 내보내기")
    st.caption("내 모든 일기와 AI 피드백을 JSON 파일로 받아갈 수 있습니다. (백업, 다른 도구로 이전 등)")

    try:
        all_rows = (
            supabase.table("journals")
            .select("created_at, tags, content, ai_feedback")
            .order("created_at", desc=True)
            .execute()
            .data
        )

        if all_rows:
            # 사람이 읽기 좋게 변환
            export_data = [{
                "created_at_kst": to_kst_str(r["created_at"]),
                "tags": r.get("tags") or "",
                "content": r.get("content") or "",
                "ai_feedback": r.get("ai_feedback") or "",
            } for r in all_rows]

            json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
            today_str = datetime.datetime.now(KST).strftime("%Y%m%d")

            st.download_button(
                label=f"📥 내 일기 {len(all_rows)}개 JSON으로 다운로드",
                data=json_bytes,
                file_name=f"my_stock_diary_backup_{today_str}.json",
                mime="application/json",
            )
        else:
            st.info("아직 저장된 일기가 없습니다.")
    except Exception as e:
        st.error(f"데이터 조회 실패: {e}")

    st.markdown("---")
    st.markdown("### ℹ️ 데이터 저장 위치 및 프라이버시")
    st.info(
        "이 앱의 모든 데이터는 철저하게 암호화되어 **Supabase 클라우드**에 안전하게 보관됩니다.\n\n"
        "- **독립된 공간:** 다른 사용자는 본인의 일기를 절대 볼 수 없습니다 (RLS 보안 적용).\n"
        "- **AI 프라이버시:** AI 멘토와의 실시간 대화 내용이나 임시 캡처 사진은 화면을 새로고침하거나 "
        "대화를 초기화하면 즉시 휘발되며, 모델 학습에 영구적으로 저장되지 않습니다."
    )

    st.markdown("---")
    st.markdown("### 🗑️ 계정 데이터 삭제")
    st.caption("⚠️ 이 작업은 되돌릴 수 없습니다.")

    with st.expander("내 모든 일기 삭제 (주의)"):
        confirm = st.text_input('확인 문구로 "삭제합니다" 를 입력하세요', key="delete_confirm")
        if st.button("💥 내 모든 일기 영구 삭제", type="primary"):
            if confirm == "삭제합니다":
                try:
                    _uid = st.session_state["user_id"]
                    supabase.table("journals").delete().eq("user_id", _uid).execute()
                    supabase.table("trades").delete().eq("user_id", _uid).execute()
                    get_recent_journals.clear()
                    get_real_inventory.clear()
                    st.success("모든 일기와 매매 기록이 삭제되었습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 실패: {e}")
            else:
                st.warning('확인 문구를 정확히 입력해주세요.')
