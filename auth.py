import streamlit as st
from supabase import create_client
from session_utils import save_session_to_disk

def validate_password(pw: str) -> str | None:
    """비밀번호 강도를 검증합니다. 8자리 이상이며 영문자와 숫자를 모두 포함해야 함."""
    if len(pw) < 8:
        return "비밀번호는 8자리 이상으로 설정해주세요."
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return "비밀번호는 영문자와 숫자를 모두 포함해야 합니다."
    return None

def show_login(supabase_url: str, supabase_anon_key: str, dev_mode: bool) -> None:
    """로그인/회원가입/비밀번호찾기 UI. 성공 시 st.session_state에 세션 저장 후 st.rerun()."""
    st.markdown("""
    <div style="text-align: center; margin-top: 50px; margin-bottom: 40px;">
        <h1 style="font-size: 2.3rem; font-weight: 800; color: #191F28; margin-bottom: 10px;">
            <span style="color: #3182F6;">📈 AI</span> 주식 페이스메이커
        </h1>
        <p style="color: #8B95A1; font-size: 1.1rem; font-weight: 500;">흔들리지 않는 장기 투자의 시작</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🔐 로그인")
    st.caption("이메일과 비밀번호를 입력해주세요. 처음 오신 분은 회원가입을 눌러주세요.")

    # 로그인 폼
    with st.form("login_form"):
        st.markdown("#### 로그인")
        email = st.text_input("이메일", placeholder="you@example.com")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        login_btn = st.form_submit_button("✅ 로그인", type="primary", width="stretch")

    if login_btn:
        if not email or not password:
            st.warning("이메일과 비밀번호를 모두 입력해주세요.")
        else:
            try:
                client = create_client(supabase_url, supabase_anon_key)
                response = client.auth.sign_in_with_password({
                    "email": email,
                    "password": password,
                })
                if response.session:
                    st.session_state["supabase_session"] = {
                        "access_token": response.session.access_token,
                        "refresh_token": response.session.refresh_token,
                    }
                    # pyrefly: ignore [missing-attribute]
                    st.session_state["user_id"] = response.user.id
                    # pyrefly: ignore [missing-attribute]
                    st.session_state["user_email"] = response.user.email
                    save_session_to_disk(st.session_state["supabase_session"], dev_mode)
                    st.rerun()
            except Exception:
                st.error("⚠️ 로그인 실패: 이메일이나 비밀번호를 다시 확인해주세요.")

    st.markdown("---")

    # 회원가입 폼 (비밀번호 확인 포함)
    with st.expander("📝 처음 오셨나요? 회원가입"):
        with st.form("signup_form"):
            su_email = st.text_input("이메일", placeholder="you@example.com", key="su_email")
            su_password = st.text_input("비밀번호", type="password", placeholder="8자리 이상 (영문+숫자 포함)", key="su_pw")
            su_password2 = st.text_input("비밀번호 확인", type="password", placeholder="비밀번호를 한 번 더 입력하세요", key="su_pw2")
            signup_btn = st.form_submit_button("🎉 회원가입", type="primary", width="stretch")

    if signup_btn:
        if not su_email or not su_password or not su_password2:
            st.warning("모든 항목을 입력해주세요.")
        elif su_password != su_password2:
            st.error("❌ 비밀번호가 일치하지 않습니다. 다시 확인해주세요.")
        elif validate_password(su_password):
            st.warning(validate_password(su_password))
        else:
            try:
                client = create_client(supabase_url, supabase_anon_key)
                client.auth.sign_up({"email": su_email, "password": su_password})
                st.success("🎉 회원가입 완료! 위 로그인 폼에서 로그인해주세요.")
            except Exception as e:
                st.error(f"⚠️ 회원가입 실패: {e}")

    st.markdown("---")

    # 비밀번호 찾기 (3단계: 이메일 → 인증코드 → 새 비밀번호)
    with st.expander("🔑 비밀번호를 잊으셨나요?"):
        step = st.session_state.get("pw_reset_step", "email")

        if step == "email":
            with st.form("reset_email_form"):
                reset_email = st.text_input("가입한 이메일", placeholder="you@example.com")
                send_btn = st.form_submit_button("📨 인증코드 받기", type="primary", width="stretch")
            if send_btn:
                if not reset_email:
                    st.warning("이메일을 입력해주세요.")
                else:
                    try:
                        client = create_client(supabase_url, supabase_anon_key)
                        client.auth.sign_in_with_otp({
                            "email": reset_email,
                            "options": {"should_create_user": False},
                        })
                        st.session_state["pw_reset_email"] = reset_email
                        st.session_state["pw_reset_step"] = "otp"
                        st.success(f"📧 {reset_email}로 인증코드를 보냈습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"발송 실패: {e}")

        elif step == "otp":
            st.info(f"📧 **{st.session_state.get('pw_reset_email')}** 으로 인증코드를 보냈습니다.")
            with st.form("reset_otp_form"):
                otp_code = st.text_input("이메일로 받은 인증코드", max_chars=8, placeholder="6~8자리")
                otp_btn = st.form_submit_button("✅ 확인", type="primary", width="stretch")
            if otp_btn:
                if not otp_code:
                    st.warning("인증코드를 입력해주세요.")
                else:
                    try:
                        client = create_client(supabase_url, supabase_anon_key)
                        response = client.auth.verify_otp({
                            "email": st.session_state["pw_reset_email"],
                            "token": otp_code,
                            "type": "recovery",  # [수정] 비밀번호 재설정 목적에 맞는 type
                        })
                        if response.session:
                            st.session_state["pw_reset_session"] = {
                                "access_token": response.session.access_token,
                                "refresh_token": response.session.refresh_token,
                            }
                            st.session_state["pw_reset_step"] = "new_password"
                            st.rerun()
                    except Exception as e:
                        st.error(f"인증 실패: {e}")

        elif step == "new_password":
            st.success("✅ 본인 확인 완료! 새 비밀번호를 설정해주세요.")
            with st.form("reset_newpw_form"):
                new_pw = st.text_input("새 비밀번호", type="password", placeholder="8자리 이상 (영문+숫자 포함)")
                new_pw2 = st.text_input("새 비밀번호 확인", type="password")
                save_btn = st.form_submit_button("🔒 비밀번호 변경", type="primary", width="stretch")
            if save_btn:
                if not new_pw or not new_pw2:
                    st.warning("비밀번호를 입력해주세요.")
                elif new_pw != new_pw2:
                    st.error("❌ 비밀번호가 일치하지 않습니다.")
                elif validate_password(new_pw):
                    st.warning(validate_password(new_pw))
                else:
                    try:
                        reset_client = create_client(supabase_url, supabase_anon_key)
                        rs = st.session_state["pw_reset_session"]
                        reset_client.auth.set_session(rs["access_token"], rs["refresh_token"])
                        reset_client.auth.update_user({"password": new_pw})
                        st.success("✅ 비밀번호가 변경되었습니다! 위 로그인 폼에서 로그인해주세요.")
                        for k in ["pw_reset_step", "pw_reset_email", "pw_reset_session"]:
                            st.session_state.pop(k, None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"변경 실패: {e}")
