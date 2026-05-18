import streamlit as st
import json
import datetime
from db import to_kst_str, KST, get_recent_journals, get_real_inventory
from ui_components import card, banner

def render_settings_tab(supabase):
    st.markdown("### ⚙️ 설정 및 데이터 관리")
    st.markdown("<p style='color: #4E5968; font-size: 0.95em;'>비밀번호를 재설정하거나 안전하게 데이터를 백업 및 삭제할 수 있습니다.</p>", unsafe_allow_html=True)

    # 1. 비밀번호 변경
    st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🔑 비밀번호 변경")
    
    with st.form("change_pw_form", clear_on_submit=True):
        cp_new = st.text_input("새 비밀번호", type="password", placeholder="6자리 이상 입력해주세요")
        cp_new2 = st.text_input("새 비밀번호 확인", type="password", placeholder="한번 더 입력해주세요")
        cp_btn = st.form_submit_button("🔒 변경 사항 저장", type="primary")
        
    if cp_btn:
        if not cp_new or not cp_new2:
            banner("비밀번호 항목을 모두 입력해주세요.", type="warning")
        elif cp_new != cp_new2:
            banner("입력하신 두 비밀번호가 일치하지 않습니다.", type="error")
        elif len(cp_new) < 6:
            banner("비밀번호는 최소 6자리 이상이어야 합니다.", type="warning")
        else:
            try:
                supabase.auth.update_user({"password": cp_new})
                banner("비밀번호가 성공적으로 변경되었습니다. 🎉", type="success")
            except Exception as e:
                banner(f"변경에 실패했습니다: {e}", type="error")

    # 2. 내 일기 데이터 내보내기
    st.markdown("---")
    st.markdown("#### 💾 데이터 내보내기 및 백업")
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em; margin-bottom: 12px;'>사용자가 기록한 모든 주식 일기와 AI 피드백을 JSON 파일로 즉시 다운로드하여 소장할 수 있습니다.</p>", unsafe_allow_html=True)

    try:
        _uid = st.session_state.get("user_id")
        all_rows = (
            supabase.table("journals")
            .select("created_at, tags, content, ai_feedback")
            .eq("user_id", _uid)
            .order("created_at", desc=True)
            .execute()
            .data
        )

        if all_rows:
            export_data = [{
                "created_at_kst": to_kst_str(r["created_at"]),
                "tags": r.get("tags") or "",
                "content": r.get("content") or "",
                "ai_feedback": r.get("ai_feedback") or "",
            } for r in all_rows]

            json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
            today_str = datetime.datetime.now(KST).strftime("%Y%m%d")

            st.download_button(
                label=f"📥 내 일기 {len(all_rows)}개 백업 파일 다운로드 (.json)",
                data=json_bytes,
                file_name=f"my_stock_diary_backup_{today_str}.json",
                mime="application/json",
            )
        else:
            banner("아직 저장된 일기가 없어서 백업을 생성할 수 없습니다.", type="info")
    except Exception as e:
        banner(f"백업 데이터 조회 실패: {e}", type="error")

    # 3. 데이터 보안 및 프라이버시 안내
    st.markdown("---")
    st.markdown("#### 🛡️ 데이터 보안 및 개인정보 처리방침")
    
    security_info = """
    이 서비스의 모든 개인 데이터는 철저하게 암호화되어 글로벌 보안 표준을 준수하는 <b>Supabase Cloud</b> 데이터베이스에 안전하게 보관됩니다.
    <br><br>
    <ul>
        <li><b>독립된 유저 공간:</b> 개별 사용자 정보는 행 단위 보안 정책(RLS, Row Level Security)에 의해 타인이 절대 조회할 수 없도록 철저히 격리됩니다.</li>
        <li><b>휘발성 AI 분석:</b> AI 멘토와의 일시적인 대화나 분석 목적의 캡처 이미지는 저장되지 않고 세션 종료 즉시 메모리에서 영구 삭제됩니다.</li>
    </ul>
    """
    card("안전한 데이터 보관 환경", security_info, icon="🔒")

    # 4. 계정 데이터 영구 삭제
    st.markdown("---")
    st.markdown("<h4 style='color: #E03131;'>⚠️ 계정 데이터 삭제</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em;'>이 작업은 복구가 불가능합니다. 신중히 결정해 주세요.</p>", unsafe_allow_html=True)

    with st.expander("🚨 나의 기록 데이터 영구 삭제"):
        st.caption("⚠️ 주의: 일기 및 매매 기록만 삭제됩니다. 계정(이메일/비밀번호)은 유지되므로 같은 계정으로 다시 로그인할 수 있습니다.")
        confirm = st.text_input('본인 확인을 위해 아래 입력창에 "삭제합니다"를 입력해주세요', key="delete_confirm")
        if st.button("💥 내 기록 데이터 영구 삭제", type="primary"):
            if confirm == "삭제합니다":
                try:
                    _uid = st.session_state["user_id"]
                    supabase.table("journals").delete().eq("user_id", _uid).execute()
                    supabase.table("trades").delete().eq("user_id", _uid).execute()
                    get_recent_journals.clear()
                    get_real_inventory.clear()
                    # 세션도 완전히 비워서 로그아웃 상태로 전환
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
                except Exception as e:
                    banner(f"삭제에 실패했습니다: {e}", type="error")
            else:
                banner("확인 문구가 정확하지 않습니다. 다시 입력해주세요.", type="warning")
