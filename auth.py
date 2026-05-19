import streamlit as st
from supabase import create_client
from session_utils import (
    save_session_to_disk,
    save_pin_cache, load_pin_cache, clear_pin_cache, hash_pin,
)

MAX_PIN_ATTEMPTS = 5


def validate_password(pw: str) -> str | None:
    """비밀번호 강도 검증. 문제 없으면 None 반환."""
    if len(pw) < 8:
        return "비밀번호는 8자리 이상으로 설정해주세요."
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return "비밀번호는 영문자와 숫자를 모두 포함해야 합니다."
    return None


def _mask_email(email: str) -> str:
    """이메일 앞 3자만 표시하고 나머지 마스킹."""
    if "@" not in email:
        return email[:3] + "***"
    local, domain = email.split("@", 1)
    visible = local[:3] if len(local) >= 3 else local
    return f"{visible}***@{domain}"


def _show_header():
    st.markdown("""
    <div style="text-align: center; margin-top: 50px; margin-bottom: 40px;">
        <h1 style="font-size: 2.3rem; font-weight: 800; color: #191F28; margin-bottom: 10px;">
            <span style="color: #3182F6;">📈 AI</span> 주식 페이스메이커
        </h1>
        <p style="color: #8B95A1; font-size: 1.1rem; font-weight: 500;">흔들리지 않는 장기 투자의 시작</p>
    </div>
    """, unsafe_allow_html=True)


def _restore_session_from_cache(
    pin_data: dict, supabase_url: str, supabase_anon_key: str, dev_mode: bool
) -> bool:
    """PIN 캐시의 토큰으로 Supabase 세션 복구. 성공 시 True."""
    try:
        client = create_client(supabase_url, supabase_anon_key)
        resp = client.auth.set_session(
            access_token=pin_data["access_token"],
            refresh_token=pin_data["refresh_token"],
        )
        if resp and resp.session:
            session = {
                "access_token": resp.session.access_token,
                "refresh_token": resp.session.refresh_token,
            }
            st.session_state["supabase_session"] = session
            st.session_state["user_id"] = resp.user.id
            st.session_state["user_email"] = resp.user.email
            # 갱신된 토큰을 PIN 캐시에 반영
            save_pin_cache(session, pin_data["pin_hash"], pin_data.get("email", ""))
            save_session_to_disk(session, dev_mode)
            return True
    except Exception:
        pass
    return False


# ── 화면 1: PIN 입력 ─────────────────────────────────────

def _show_pin_entry(
    pin_data: dict, supabase_url: str, supabase_anon_key: str, dev_mode: bool
):
    email = pin_data.get("email", "")
    attempts = st.session_state.get("_pin_attempts", 0)

    st.markdown(f"""
    <div style="text-align:center; padding:16px; background:#F0F4FF;
                border-radius:16px; margin-bottom:24px;">
        <p style="font-size:0.85rem; color:#8B95A1; margin:0 0 4px;">저장된 계정</p>
        <p style="font-size:1.1rem; font-weight:700; color:#191F28; margin:0;">
            {_mask_email(email)}
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔒 PIN 번호 입력")

    if attempts > 0:
        remaining = MAX_PIN_ATTEMPTS - attempts
        st.warning(f"❌ PIN이 틀렸습니다. 남은 시도: **{remaining}회**")

    with st.form("pin_entry_form"):
        pin = st.text_input(
            "PIN",
            type="password",
            max_chars=4,
            placeholder="숫자 4자리",
            label_visibility="collapsed",
        )
        submit = st.form_submit_button("✅ 확인", type="primary", use_container_width=True)

    if submit:
        if len(pin) != 4 or not pin.isdigit():
            st.warning("숫자 4자리를 입력해주세요.")
        elif hash_pin(pin) == pin_data.get("pin_hash"):
            # ✅ PIN 일치 → 세션 복구
            if _restore_session_from_cache(pin_data, supabase_url, supabase_anon_key, dev_mode):
                st.session_state.pop("_pin_attempts", None)
                st.rerun()
            else:
                # 토큰 만료 → PIN 캐시 삭제 후 풀 로그인
                clear_pin_cache()
                st.session_state.pop("_pin_attempts", None)
                st.session_state["_show_full_login"] = True
                st.error("⚠️ 세션이 만료되었습니다. 다시 로그인해주세요.")
                st.rerun()
        else:
            # ❌ PIN 불일치
            new_attempts = attempts + 1
            st.session_state["_pin_attempts"] = new_attempts
            if new_attempts >= MAX_PIN_ATTEMPTS:
                clear_pin_cache()
                st.session_state.pop("_pin_attempts", None)
                st.session_state["_show_full_login"] = True
                st.rerun()
            else:
                st.rerun()

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔑 이메일로 로그인", use_container_width=True):
            st.session_state["_show_full_login"] = True
            st.rerun()
    with col2:
        if st.button("🗑️ PIN 초기화", use_container_width=True):
            clear_pin_cache()
            st.session_state["_show_full_login"] = True
            st.rerun()


# ── 화면 2: PIN 설정 (최초 로그인 후) ────────────────────

def _show_pin_setup(dev_mode: bool):
    pending_session = st.session_state.get("_pending_session", {})
    pending_email = st.session_state.get("_pending_email", "")

    st.markdown("### 🔒 PIN 번호 설정")
    st.info("📱 다음부터 4자리 PIN으로 빠르게 로그인할 수 있어요!\n\n숫자 4자리로 나만의 PIN을 만들어보세요.")

    with st.form("pin_setup_form"):
        pin1 = st.text_input(
            "PIN 번호 (숫자 4자리)", type="password", max_chars=4, placeholder="0000"
        )
        pin2 = st.text_input(
            "PIN 번호 확인", type="password", max_chars=4, placeholder="0000"
        )
        col1, col2 = st.columns(2)
        with col1:
            save_btn = st.form_submit_button("✅ PIN 설정", type="primary", use_container_width=True)
        with col2:
            skip_btn = st.form_submit_button("건너뛰기", use_container_width=True)

    if save_btn:
        if len(pin1) != 4 or not pin1.isdigit():
            st.warning("숫자 4자리를 입력해주세요.")
        elif pin1 != pin2:
            st.error("❌ PIN이 일치하지 않습니다.")
        else:
            save_pin_cache(pending_session, hash_pin(pin1), pending_email)
            save_session_to_disk(pending_session, dev_mode)
            st.session_state["supabase_session"] = pending_session
            for k in ["_pending_session", "_pending_email", "_show_pin_setup"]:
                st.session_state.pop(k, None)
            st.rerun()

    if skip_btn:
        save_session_to_disk(pending_session, dev_mode)
        st.session_state["supabase_session"] = pending_session
        for k in ["_pending_session", "_pending_email", "_show_pin_setup"]:
            st.session_state.pop(k, None)
        st.rerun()


# ── 화면 3: 이메일/비밀번호 풀 로그인 ───────────────────

def _show_full_login_form(supabase_url: str, supabase_anon_key: str, dev_mode: bool):
    st.markdown("### 🔐 로그인")
    st.caption("이메일과 비밀번호를 입력해주세요. 처음 오신 분은 회원가입을 눌러주세요.")

    with st.form("login_form"):
        st.markdown("#### 로그인")
        email = st.text_input("이메일", placeholder="you@example.com")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        login_btn = st.form_submit_button("✅ 로그인", type="primary", use_container_width=True)

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
                    session = {
                        "access_token": response.session.access_token,
                        "refresh_token": response.session.refresh_token,
                    }
                    user_email = response.user.email
                    st.session_state["user_id"] = response.user.id
                    st.session_state["user_email"] = user_email

                    existing = load_pin_cache()
                    if existing and existing.get("pin_hash"):
                        # 기존 PIN 유지 + 새 세션 토큰 업데이트
                        save_pin_cache(session, existing["pin_hash"], user_email)
                        save_session_to_disk(session, dev_mode)
                        st.session_state["supabase_session"] = session
                        st.session_state.pop("_show_full_login", None)
                        st.rerun()
                    else:
                        # PIN 미설정 → PIN 설정 화면으로
                        st.session_state["_pending_session"] = session
                        st.session_state["_pending_email"] = user_email
                        st.session_state["_show_pin_setup"] = True
                        st.session_state.pop("_show_full_login", None)
                        st.rerun()
            except Exception:
                st.error("⚠️ 로그인 실패: 이메일이나 비밀번호를 다시 확인해주세요.")

    st.markdown("---")

    # 회원가입
    with st.expander("📝 처음 오셨나요? 회원가입"):
        with st.form("signup_form"):
            su_email = st.text_input("이메일", placeholder="you@example.com", key="su_email")
            su_password = st.text_input(
                "비밀번호", type="password", placeholder="8자리 이상 (영문+숫자 포함)", key="su_pw"
            )
            su_password2 = st.text_input(
                "비밀번호 확인", type="password", placeholder="비밀번호를 한 번 더 입력하세요", key="su_pw2"
            )
            signup_btn = st.form_submit_button("🎉 회원가입", type="primary", use_container_width=True)

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

    # 비밀번호 찾기 (3단계: 이메일 → OTP → 새 비밀번호)
    with st.expander("🔑 비밀번호를 잊으셨나요?"):
        step = st.session_state.get("pw_reset_step", "email")

        if step == "email":
            with st.form("reset_email_form"):
                reset_email = st.text_input("가입한 이메일", placeholder="you@example.com")
                send_btn = st.form_submit_button("📨 인증코드 받기", type="primary", use_container_width=True)
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
                otp_btn = st.form_submit_button("✅ 확인", type="primary", use_container_width=True)
            if otp_btn:
                if not otp_code:
                    st.warning("인증코드를 입력해주세요.")
                else:
                    try:
                        client = create_client(supabase_url, supabase_anon_key)
                        response = client.auth.verify_otp({
                            "email": st.session_state["pw_reset_email"],
                            "token": otp_code,
                            "type": "recovery",
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
                new_pw = st.text_input(
                    "새 비밀번호", type="password", placeholder="8자리 이상 (영문+숫자 포함)"
                )
                new_pw2 = st.text_input("새 비밀번호 확인", type="password")
                save_btn = st.form_submit_button("🔒 비밀번호 변경", type="primary", use_container_width=True)
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


# ── 메인 진입점 ──────────────────────────────────────────

def show_login(supabase_url: str, supabase_anon_key: str, dev_mode: bool) -> None:
    """로그인 화면. 상태에 따라 PIN 입력 / PIN 설정 / 풀 로그인을 라우팅."""
    _show_header()

    # 상태 1: 로그인 직후 PIN 설정
    if st.session_state.get("_show_pin_setup"):
        _show_pin_setup(dev_mode)
        return

    pin_data = load_pin_cache()
    has_valid_cache = (
        pin_data
        and pin_data.get("pin_hash")
        and pin_data.get("access_token")
    )

    # 상태 2: PIN 캐시 있고 풀 로그인 요청 없음 → PIN 입력
    if has_valid_cache and not st.session_state.get("_show_full_login"):
        _show_pin_entry(pin_data, supabase_url, supabase_anon_key, dev_mode)
        return

    # 상태 3: 풀 로그인
    _show_full_login_form(supabase_url, supabase_anon_key, dev_mode)
