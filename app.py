import streamlit as st
import google.generativeai as genai
import os
import json
import re
import math
import datetime
from datetime import timezone, timedelta
from pathlib import Path
from prices import TICKER_MAP, get_realtime_prices_bulk, get_realtime_price, get_usd_to_krw, _market_time_bucket


# [변경] 이미지 처리 라이브러리는 그대로
from PIL import Image, ImageDraw

# [변경] sqlite3 → supabase
from supabase import create_client, Client

# 한국 시간대 상수 (UTC+9)
KST = timezone(timedelta(hours=9))

# 2. 앱 기본 설정
st.set_page_config(page_title="AI 주식 다이어리", page_icon="📈", layout="centered")

# ==========================================
# 🧠 전역 세션 상태 초기화 (탭 진입 전 보장)
# ==========================================
if 'daily_stock_list' not in st.session_state:
    st.session_state['daily_stock_list'] = []
if 'current_step' not in st.session_state:
    st.session_state['current_step'] = 'upload_mode'
if 'current_tags' not in st.session_state:
    st.session_state['current_tags'] = []
if 'chat_messages' not in st.session_state:
    st.session_state['chat_messages'] = []
if 'uploader_key' not in st.session_state:
    st.session_state['uploader_key'] = 0

# ---------------------------------------------------------
# 🎨 [추가] 모바일 최적화 UI 테마 (토스 스타일)
# ---------------------------------------------------------
toss_style = """
<style>
    /* 1. 폰트 변경 (Pretendard 적용) */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif !important;
    }

    /* 2. 전체 배경색 및 텍스트 색상 (밝고 깔끔하게) */
    .stApp {
        background-color: #F9FAFB; /* 아주 연한 회색 배경 */
        color: #191F28; /* 너무 까맣지 않은 부드러운 검정 텍스트 */
    }

    /* 3. 불필요한 기본 UI 숨기기 (진짜 앱처럼) */
    #MainMenu {visibility: hidden;} /* 우측 상단 햄버거 메뉴 숨김 */
    footer {visibility: hidden;}    /* 하단 Streamlit 워터마크 숨김 */
    header {visibility: hidden;}    /* 상단 헤더 공간 숨김 */
    
    /* 4. 버튼 디자인 (메인 / 보조 분리) */
    
    /* 🔵 메인 버튼 ('보내기', '저장' 등 type="primary") */
    button[kind="primary"], button[kind="primaryFormSubmit"] {
        background-color: #3182F6 !important; /* 토스 블루 */
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        width: 100% !important;
        box-shadow: 0 4px 6px rgba(49, 130, 246, 0.2) !important;
        transition: all 0.2s ease-in-out !important;
    }
    button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
        background-color: #1B64DA !important; /* 마우스 오버 시 짙어짐 */
        transform: translateY(-2px) !important;
    }

    /* ⚪ 보조 버튼 ('대화 초기화', '취소' 등 일반 버튼) */
    button[kind="secondary"], button[kind="secondaryFormSubmit"] {
        background-color: #F2F4F6 !important; /* 연한 회색 배경 */
        color: #4E5968 !important; /* 짙은 회색 글자 */
        border-radius: 12px !important;
        border: none !important;
        padding: 12px 16px !important;
        font-weight: 600 !important;
        width: 100% !important;
        transition: all 0.2s ease-in-out !important;
    }
    button[kind="secondary"]:hover, button[kind="secondaryFormSubmit"]:hover {
        background-color: #E5E8EB !important; /* 마우스 오버 시 살짝 어두워짐 */
        color: #333D4B !important;
    }

    /* 5. 입력창(폼), 사진 업로드 박스 디자인 */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        background-color: #FFFFFF !important;
        border-radius: 12px !important;
        border: 1px solid #E5E8EB !important;
        padding: 12px !important;
    }
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border: 2px solid #3182F6 !important; /* 입력 시 파란색 테두리 하이라이트 */
    }

    /* 6. 정보 박스 (Expander/Info) 디자인 */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF;
        border-radius: 16px;
        border: 1px solid #E5E8EB;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        margin-bottom: 12px;
    }
    div[data-testid="stAlert"] {
        border-radius: 12px;
        border: none;
    }

    /* 7. 모바일 뷰 여백 최적화 */
    .block-container {
        padding-top: 2rem !important; /* 상단 여백 줄임 */
        padding-bottom: 4rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 600px !important; /* 모바일 앱처럼 폭을 제한 */
    }
</style>
"""
st.markdown(toss_style, unsafe_allow_html=True)
# ---------------------------------------------------------

# [변경] 사용할 Gemini 모델 (그대로)
MODEL_NAME = "gemini-3-flash-preview"

# ==========================================
# 🔐 [변경] 비밀키 로드 — st.secrets 사용
#   로컬: .streamlit/secrets.toml
#   클라우드: Streamlit Cloud의 Secrets 메뉴
# ==========================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception as e:
    st.error("⚠️ 비밀키를 읽어오지 못했습니다.")
    st.info(
        "**해결 방법:**\n"
        "1. 프로젝트 폴더에 `.streamlit/secrets.toml` 파일을 만들고\n"
        "2. 다음 3가지 값을 채워주세요:\n"
        "```toml\n"
        'SUPABASE_URL = "https://xxxx.supabase.co"\n'
        'SUPABASE_ANON_KEY = "eyJhbGc..."\n'
        'GEMINI_API_KEY = "AIza..."\n'
        "```"
    )
    st.write(f"상세: `{e}`")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)


# ==========================================
# 🛠️ [추가] 개발 모드 — 매번 로그인 안 해도 되게 세션 유지
#   secrets.toml에 DEV_MODE = true 를 추가하면 활성화
#   본인 PC에서만 사용. 클라우드 배포 시엔 반드시 false 또는 삭제!
# ==========================================
DEV_MODE = st.secrets.get("DEV_MODE", False)
SESSION_CACHE_PATH = Path(".streamlit") / "session_cache.json"

def save_session_to_disk(session_dict: dict) -> None:
    """DEV_MODE일 때만 세션을 로컬 파일에 저장."""
    if not DEV_MODE:
        return
    try:
        SESSION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_CACHE_PATH.write_text(json.dumps(session_dict), encoding="utf-8")
    except Exception:
        pass

def load_session_from_disk() -> dict | None:
    """DEV_MODE일 때만 디스크에서 세션 복구 시도."""
    if not DEV_MODE:
        return None
    try:
        if SESSION_CACHE_PATH.exists():
            return json.loads(SESSION_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None

def clear_session_from_disk() -> None:
    try:
        if SESSION_CACHE_PATH.exists():
            SESSION_CACHE_PATH.unlink()
    except Exception:
        pass

# [추가] 앱 시작 시 디스크 세션 자동 복구 시도 (DEV_MODE 한정)
if DEV_MODE and "supabase_session" not in st.session_state:
    cached = load_session_from_disk()
    if cached:
        try:
            _temp_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            _resp = _temp_client.auth.set_session(
                access_token=cached["access_token"],
                refresh_token=cached["refresh_token"],
            )
            if _resp and _resp.session:
                # 토큰이 만료 직전이면 set_session이 자동 갱신해서 새 토큰을 줌
                st.session_state["supabase_session"] = {
                    "access_token": _resp.session.access_token,
                    "refresh_token": _resp.session.refresh_token,
                }
                st.session_state["user_id"] = _resp.user.id
                st.session_state["user_email"] = _resp.user.email
                # 갱신된 토큰을 다시 저장
                save_session_to_disk(st.session_state["supabase_session"])
        except Exception:
            # 세션 만료/오류 → 캐시 폐기, 정상 로그인 흐름으로
            clear_session_from_disk()


# ==========================================
# 🔌 [변경] Supabase 클라이언트 — 사용자 세션을 매번 주입
#   기존 init_db()가 하던 역할을 대체
# ==========================================
def get_supabase() -> Client:
    """현재 로그인된 사용자의 세션을 가진 Supabase 클라이언트 반환."""
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    session = st.session_state.get("supabase_session")
    if session:
        try:
            client.auth.set_session(
                access_token=session["access_token"],
                refresh_token=session["refresh_token"],
            )
        except Exception:
            # 세션 만료 시 자동 로그아웃
            st.session_state.pop("supabase_session", None)
            st.session_state.pop("user_id", None)
            st.rerun()

    return client


# ==========================================
# 🔑 로그인 화면 — 이메일 & 비밀번호 방식
# ==========================================
def show_login():
    st.title("📈 AI 주식 페이스메이커")
    st.markdown("### 🔐 로그인")
    st.caption("이메일과 비밀번호를 입력해주세요. 처음 오신 분은 회원가입을 눌러주세요.")

    # 로그인 폼
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
                client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
                response = client.auth.sign_in_with_password({
                    "email": email,
                    "password": password,
                })
                if response.session:
                    st.session_state["supabase_session"] = {
                        "access_token": response.session.access_token,
                        "refresh_token": response.session.refresh_token,
                    }
                    st.session_state["user_id"] = response.user.id
                    st.session_state["user_email"] = response.user.email
                    save_session_to_disk(st.session_state["supabase_session"])
                    st.rerun()
            except Exception:
                st.error("⚠️ 로그인 실패: 이메일이나 비밀번호를 다시 확인해주세요.")

    st.markdown("---")

    # 회원가입 폼 (비밀번호 확인 포함)
    with st.expander("📝 처음 오셨나요? 회원가입"):
        with st.form("signup_form"):
            su_email = st.text_input("이메일", placeholder="you@example.com", key="su_email")
            su_password = st.text_input("비밀번호", type="password", placeholder="6자리 이상", key="su_pw")
            su_password2 = st.text_input("비밀번호 확인", type="password", placeholder="비밀번호를 한 번 더 입력하세요", key="su_pw2")
            signup_btn = st.form_submit_button("🎉 회원가입", type="primary", use_container_width=True)

    if signup_btn:
        if not su_email or not su_password or not su_password2:
            st.warning("모든 항목을 입력해주세요.")
        elif su_password != su_password2:
            st.error("❌ 비밀번호가 일치하지 않습니다. 다시 확인해주세요.")
        elif len(su_password) < 6:
            st.warning("비밀번호는 6자리 이상으로 설정해주세요.")
        else:
            try:
                client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
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
                send_btn = st.form_submit_button("📨 인증코드 받기", type="primary", use_container_width=True)
            if send_btn:
                if not reset_email:
                    st.warning("이메일을 입력해주세요.")
                else:
                    try:
                        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
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
                        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
                        response = client.auth.verify_otp({
                            "email": st.session_state["pw_reset_email"],
                            "token": otp_code,
                            "type": "email",
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
                new_pw = st.text_input("새 비밀번호", type="password", placeholder="6자리 이상")
                new_pw2 = st.text_input("새 비밀번호 확인", type="password")
                save_btn = st.form_submit_button("🔒 비밀번호 변경", type="primary", use_container_width=True)
            if save_btn:
                if not new_pw or not new_pw2:
                    st.warning("비밀번호를 입력해주세요.")
                elif new_pw != new_pw2:
                    st.error("❌ 비밀번호가 일치하지 않습니다.")
                elif len(new_pw) < 6:
                    st.warning("6자리 이상으로 설정해주세요.")
                else:
                    try:
                        reset_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
                        rs = st.session_state["pw_reset_session"]
                        reset_client.auth.set_session(rs["access_token"], rs["refresh_token"])
                        reset_client.auth.update_user({"password": new_pw})
                        st.success("✅ 비밀번호가 변경되었습니다! 위 로그인 폼에서 로그인해주세요.")
                        for k in ["pw_reset_step", "pw_reset_email", "pw_reset_session"]:
                            st.session_state.pop(k, None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"변경 실패: {e}")


# [추가] 로그인 안 되어 있으면 여기서 멈춤
if not st.session_state.get("supabase_session"):
    show_login()
    st.stop()

# [추가] 로그인 완료 후 사용할 Supabase 클라이언트
supabase = get_supabase()

# 로그인 직후 Supabase user_metadata에서 멘토 설정 복구
if "chosen_mentor" not in st.session_state:
    try:
        user_resp = supabase.auth.get_user()
        if user_resp and user_resp.user:
            saved = (user_resp.user.user_metadata or {}).get("chosen_mentor")
            if saved:
                st.session_state["chosen_mentor"] = saved
    except Exception:
        pass


# ==========================================
# 🕒 [추가] 타임스탬프 변환 헬퍼
#   Postgres의 timestamptz는 ISO 8601 형식으로 옴
#   → KST로 변환해서 기존 코드 형식과 호환되게 만듦
# ==========================================
def to_kst_str(iso_ts: str) -> str:
    """Postgres timestamptz → 'YYYY-MM-DD HH:MM:SS' (KST)"""
    if not iso_ts:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_ts


# ==========================================
# 📊 [Phase 3] 30일 윈도우 점수 계산 — Supabase 버전
# ==========================================
def calculate_scores():
    # 30일 전 시점 (UTC ISO 형식으로 Postgres에 전달)
    thirty_days_ago = (
        datetime.datetime.now(timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()

    try:
        response = (
            supabase.table("journals")
            .select("created_at, tags")
            .gte("created_at", thirty_days_ago)
            .order("created_at", desc=True)
            .execute()
        )
        rows = response.data
    except Exception as e:
        st.sidebar.warning(f"점수 조회 실패: {e}")
        rows = []

    tags_list = [r["tags"] for r in rows if r.get("tags")]
    # KST 기준으로 날짜만 뽑아냄
    dates = sorted(
        list(set([to_kst_str(r["created_at"]).split()[0] for r in rows if r.get("created_at")])),
        reverse=True
    )

    # ▼ 점수 로직은 그대로 유지 ▼
    # 1. 원칙 준수
    routine_count = sum(1 for t in tags_list if "#월급날정기매수" in t)
    dividend_count = sum(1 for t in tags_list if "#배당금달달해" in t)
    principle = min((routine_count * 70) + (dividend_count * 30), 100)

    # 2. 멘탈 방어
    panic_count = sum(1 for t in tags_list if "#뇌동매매반성" in t)
    mental = max(100 - (panic_count * 30), 0)

    # 3. 자기 객관화
    review_count = sum(1 for t in tags_list if "#오늘의실수" in t)
    review = min(review_count * 25, 100)

    # 4. 성실도 (Streak)
    streak = 0
    today = datetime.datetime.now(KST).date()
    yesterday = today - datetime.timedelta(days=1)

    if dates:
        first_record_date = datetime.datetime.strptime(dates[0], "%Y-%m-%d").date()
        if first_record_date == today or first_record_date == yesterday:
            current_check_date = first_record_date
            for d_str in dates:
                d = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                if d == current_check_date:
                    streak += 1
                    current_check_date -= datetime.timedelta(days=1)
                else:
                    break

    consistency = min(streak * 3.3, 100)
    return {"원칙 준수": principle, "멘탈 방어": mental, "성실도": consistency, "자기 객관화": review}


def render_radar_chart(scores):
    import plotly.graph_objects as go
    categories = list(scores.keys())
    values = list(scores.values())
    categories.append(categories[0])
    values.append(values[0])

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        line_color='#d9f99d',
        fillcolor='rgba(217, 249, 157, 0.4)'
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color='gray', gridcolor='rgba(255,255,255,0.2)'),
            angularaxis=dict(tickfont=dict(size=12)),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=55, r=55, t=40, b=40),
        showlegend=False,
        height=320
    )
    return fig


# ==========================================
# ⏳ [Phase 3] 타임캡슐 — Supabase 버전
# ==========================================
def get_past_context(tags):
    """현재 선택된 태그 중 가장 중요한 감정 태그를 찾아 과거 일기를 소환."""
    if not tags:
        return ""

    priority_keywords = ["#뇌동매매반성", "#오늘좀흔들", "#오늘의실수"]
    core_tag = None

    for t in tags:
        if any(keyword in t for keyword in priority_keywords):
            core_tag = t
            break

    if not core_tag:
        core_tag = tags[0]

    try:
        response = (
            supabase.table("journals")
            .select("created_at, content")
            .like("tags", f"%{core_tag}%")
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
        rows = response.data
    except Exception:
        rows = []

    if not rows:
        return ""

    context = f"\n\n[참고 데이터: 사용자의 과거 '{core_tag}' 관련 기록]\n"
    for r in rows:
        date_str = to_kst_str(r["created_at"]).split()[0]
        context += f"- {date_str}: {r['content']}\n"
    return context


def has_tag(selected_tags, tag_keyword):
    return any(tag_keyword in t for t in selected_tags)


def safe_generate(model, content, fallback_msg="AI 분석 중 오류가 발생했어요."):
    """Gemini API 호출 안전망 (기존 그대로)."""
    try:
        response = model.generate_content(content)
        if not response.candidates or not getattr(response, 'text', None):
            return None, "⚠️ AI가 응답을 만들 수 없었어요. (안전 필터에 걸렸거나 빈 응답)"
        return response.text, None
    except Exception as e:
        return None, f"⚠️ {fallback_msg}\n\n상세: `{type(e).__name__}: {e}`"


# [변경] 최근 일기 조회 — Supabase 버전 + 사용자별 캐시
@st.cache_data(ttl=10)
def get_recent_journals(user_id: str, limit: int = 50):
    """user_id를 캐시 키에 포함해서 사용자별로 분리된 캐시를 사용."""
    try:
        response = (
            supabase.table("journals")
            .select("id, created_at, tags, content, ai_feedback")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    except Exception as e:
        st.error(f"일기 조회 실패: {e}")
        return []


# ==========================================
# 📦 [추가] 나의 보물함(재고) 데이터 집계 함수
# ==========================================
@st.cache_data(ttl=30)
def get_real_inventory(user_id: str):
    """trades 테이블에서 매수 내역을 가져와 종목별 총 수량과 평단가를 계산합니다.
    type='dividend' 행은 재고 계산에서 제외합니다."""
    try:
        # 배당금 기록 제외 (type='buy' 또는 type이 없는 구 데이터만 포함)
        response = (
            supabase.table("trades")
            .select("stock_name, quantity, price, currency, type")
            .or_("type.eq.buy,type.is.null")
            .execute()
        )
        trades = response.data

        if not trades:
            return []

        # 종목별로 묶어서 총수량과 총 매수금액 계산
        inventory_map = {}
        for t in trades:
            name = t.get("stock_name")
            qty = float(t.get("quantity", 0))
            price = float(t.get("price", 0))
            currency = t.get("currency", "KRW")

            if not name or qty <= 0:
                continue

            if name not in inventory_map:
                inventory_map[name] = {"총수량": 0, "총금액": 0, "통화": currency}

            inventory_map[name]["총수량"] += qty
            inventory_map[name]["총금액"] += (qty * price)

        # UI 출력용 리스트로 변환 및 평단가 계산
        result = []
        for name, data in inventory_map.items():
            if data["총수량"] > 0:
                avg_price = data["총금액"] / data["총수량"]
                result.append({
                    "종목": name,
                    "수량": data["총수량"],
                    "평단가": avg_price,
                    "통화": data["통화"]
                })
        return result
        
    except Exception as e:
        st.error(f"재고 데이터 집계 실패: {e}")
        return []


@st.cache_data(ttl=30)
def get_dividend_total(user_id: str) -> dict:
    """배당금 합계 조회. {"KRW": 원화합계, "USD": 달러합계} 형태로 반환."""
    try:
        response = (
            supabase.table("trades")
            .select("quantity, currency")
            .eq("type", "dividend")
            .execute()
        )
        totals: dict = {"KRW": 0.0, "USD": 0.0}
        for t in response.data:
            cur = t.get("currency", "KRW")
            totals[cur] = totals.get(cur, 0.0) + float(t.get("quantity", 0))
        return totals
    except Exception:
        return {"KRW": 0.0, "USD": 0.0}


# ==========================================
# 🏠 메인 화면
# ==========================================
st.markdown("""
<div style="text-align: center; margin-top: 50px; margin-bottom: 40px;">
    <h1 style="font-size: 2.3rem; font-weight: 800; color: #191F28; margin-bottom: 10px;">
        <span style="color: #3182F6;">📈 AI</span> 주식 페이스메이커
    </h1>
    <p style="color: #8B95A1; font-size: 1.1rem; font-weight: 500;">흔들리지 않는 장기 투자의 시작</p>
</div>
""", unsafe_allow_html=True)
# [추가] 사이드바 상단에 로그인 정보 + 로그아웃 버튼
st.sidebar.markdown(f"👤 **{st.session_state.get('user_email', '로그인됨')}**")
if DEV_MODE:
    st.sidebar.caption("🛠️ 개발 모드 — 세션 자동 유지 중")
if st.sidebar.button("🚪 로그아웃"):
    clear_session_from_disk()  # [추가] 디스크 세션도 함께 삭제
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# 사용자 가이드 (처음 방문 후 접혀있도록 기본 collapsed)
with st.expander("📖 사용 방법 보기", expanded=False):
    st.info("""
    **1. 데이터 기록 (Track 1)**
    - MTS 매매 내역이나 잔고를 캡처해 올리세요.
    - AI가 종목과 수량을 읽어 데이터로 저장합니다.
    - 장기 투자 성과를 숫자로 확인하세요.
    """)
    st.success("""
    **2. 멘탈 관리 (Track 2)**
    - 시장이 흔들려 불안할 때 태그를 누르세요.
    - "무섭다", "팔고 싶다" 등 짧은 감정을 쓰세요.
    - AI 멘토가 과거 기록을 바탕으로 처방을 내립니다.
    """)
    st.caption("💡 Tip: 매일 사진을 올릴 필요는 없습니다. 매매가 없는 날엔 태그 하나와 짧은 생각만 남겨보세요.")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📝 일기 작성", "📚 과거 기록 조회", "⚙️ 설정 및 백업"])

# ---------------------------------------------------------
def sync_mentor():
    mentor = st.session_state.get("persona_widget")
    if mentor:
        st.session_state["chosen_mentor"] = mentor
        try:
            supabase.auth.update_user({"data": {"chosen_mentor": mentor}})
        except Exception:
            pass


with tab1:
    # ==========================================
    # 🦇 [신규] 동굴 모드 (Zen Mode) 스위치
    # ==========================================
    zen_mode = st.toggle(
        "🦇 동굴 모드 켜기", 
        value=False, 
        help="시장이 폭락해 멘탈이 흔들릴 때 켜세요. 모든 수익률과 숫자를 가려줍니다."
    )

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
        my_portfolio = get_real_inventory(st.session_state["user_id"])

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
            div_totals = get_dividend_total(st.session_state["user_id"])
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
                            "user_id":    st.session_state["user_id"],
                            "stock_name": div_stock.strip(),
                            "quantity":   div_amount,
                            "price":      1.0,
                            "currency":   div_currency,
                            "type":       "dividend",
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

                model = genai.GenerativeModel(MODEL_NAME, system_instruction=system_instruction)
                response_text, err = safe_generate(
                    model,
                    user_input.strip(),
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
                    # ── [수정] 구형 SDK 호환을 위해 TypedDict 구조 선언 ──
                    import typing

                    class StockItem(typing.TypedDict):
                        stock_name: str
                        quantity: float
                        ticker_hint: str

                    class TradeExtraction(typing.TypedDict):
                        trades: list[StockItem]

                    # Structured Outputs 설정 적용
                    extract_model = genai.GenerativeModel(
                        MODEL_NAME,
                        generation_config=genai.GenerationConfig(
                            response_mime_type="application/json",
                            response_schema=TradeExtraction,  # 👈 딕셔너리 대신 구조화된 스키마 대입
                        ),
                    )
                    extract_prompt = (
                        "이 이미지는 MTS(모바일 트레이딩 앱) 잔고 화면입니다. "
                        "보유 중인 모든 종목명과 수량을 추출해서 trades 리스트에 빠짐없이 담아줘. "
                        "숫자에 콤마(,)나 단위는 빼고 순수 숫자만 사용해. "
                        "ticker_hint는 야후파이낸스 티커를 넣어줘: "
                        "KODEX·TIGER·ARIRANG ETF 및 한국 개별주는 빈 문자열(\"\")로 두고, "
                        "미국 주식만 AAPL·GOOGL 형식 티커를 채워줘."
                    )

                    text, err = safe_generate(extract_model, [extract_prompt, image],
                                              fallback_msg="이미지 분석 중 오류가 발생했어요.")
                

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
            parsed_json = json.loads(ai_text.strip())
            
            # [수정] List[Dict] 형태의 AI 응답을 기존의 {종목명: 수량} 딕셔너리로 역변환
            extracted_dict = {}
            if isinstance(parsed_json, dict) and "trades" in parsed_json:
                for item in parsed_json["trades"]:
                    name = item.get("stock_name")
                    qty = item.get("quantity")
                    if name and qty is not None:
                        extracted_dict[name.strip()] = float(qty)
            elif isinstance(parsed_json, dict):
                # 예외 방어용 대피선
                extracted_dict = {k: float(v) for k, v in parsed_json.items() if v is not None}
                        
        except Exception as e:
            st.error(f"AI 응답 파싱 실패 ({e}).")
            extracted_dict = {}

        current_inventory = {item["종목"]: item["수량"] for item in get_real_inventory(st.session_state["user_id"])}

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

                past_records = get_past_context(selected_tags)
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
                      "quantity": 10
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

                model = genai.GenerativeModel(
                    MODEL_NAME,
                    system_instruction=system_instruction,
                    generation_config={"response_mime_type": "application/json"}
                )

                tag_text = " ".join(selected_tags) if selected_tags else ""
                final_prompt = f"태그: {tag_text}\n\n사용자가 오늘 다음 종목들을 매수/확인했습니다:\n{all_data_str}\n\n이 내역을 바탕으로 전체적인 투자 평과 멘탈 관리 조언을 해줘."

                final_text, err = safe_generate(model, final_prompt,
                                                fallback_msg="최종 피드백 생성 중 오류가 발생했어요.")

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
                                if not ticker:
                                    hint = (trade.get("ticker_hint") or "").strip()
                                    if hint:
                                        ticker = hint
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
                                    currency   = "KRW"  # 티커 미확인 → 국내로 간주
                                trades_to_insert.append({
                                    "stock_name": trade["_normalized_name"],
                                    "quantity":   trade["quantity"],
                                    "price":      real_price,
                                    "currency":   currency,
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
    st.markdown("<br><br><br>", unsafe_allow_html=True)  # 위 콘텐츠와 간격 벌리기
    st.markdown("---")
    st.subheader("📊 나의 투자 능력치 종합")

    if zen_mode:
        st.info("🌿 **동굴 모드 작동 중**\n\n현재 점수와 능력치 차트를 숨겨두었습니다. 흔들리지 않는 멘탈이 가장 중요합니다.")
    else:
        current_scores = calculate_scores()
        radar_fig = render_radar_chart(current_scores)
        st.plotly_chart(radar_fig, use_container_width=True)
        st.info(f"🔥 현재 연속 기록(Streak): **{int(current_scores['성실도'] // 3.3)}일**")

# ---------------------------------------------------------
# 탭 2: 과거 기록 조회
with tab2:
    st.header("📚 나의 투자 기록장")

    # [변경] user_id를 캐시 키로 전달
    rows = get_recent_journals(st.session_state["user_id"])

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

# ---------------------------------------------------------
# 탭 3: 백업/복원 — [변경] JSON 내보내기/가져오기로 전환
#   .db 파일은 클라우드 DB로 갔기 때문에 의미 없음
#   대신 사용자가 본인 데이터를 언제든 추출/이전 가능하게 함
with tab3:
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
