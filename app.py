import streamlit as st
# [수정] 새로운 google-genai SDK 임포트
from google import genai
from google.genai import types
import os
import json
import re
import math
import datetime
from datetime import timezone, timedelta
from pathlib import Path
import yfinance as yf
from ui_components import render_radar_chart
from session_utils import (
    SESSION_CACHE_PATH, get_dev_mode,
    save_session_to_disk, load_session_from_disk, clear_session_from_disk,
)
from auth import show_login

# ==========================================
from tab_diary import render_diary_tab
from tab_records import render_records_tab
from tab_settings import render_settings_tab
# [변경] 이미지 처리 라이브러리는 그대로
from PIL import Image, ImageDraw

# [변경] sqlite3 → supabase
from supabase import create_client, Client

# 한국 시간대 상수 (UTC+9)
KST = timezone(timedelta(hours=9))

# ==========================================
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

# [수정] 지정하신 최신 고속 모델로 변경
MODEL_NAME = "gemini-2.0-flash-lite"

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

# [수정] 새로운 SDK의 Client 초기화
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 🛠️ [추가] 개발 모드 — 매번 로그인 안 해도 되게 세션 유지
#   secrets.toml에 DEV_MODE = true 를 추가하면 활성화
#   본인 PC에서만 사용. 클라우드 배포 시엔 반드시 false 또는 삭제!
# ==========================================
DEV_MODE = get_dev_mode(st.secrets)

# [추가] 앱 시작 시 디스크 세션 자동 복구 시도 (DEV_MODE 한정)
if DEV_MODE and "supabase_session" not in st.session_state:
    cached = load_session_from_disk(DEV_MODE)
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
                save_session_to_disk(st.session_state["supabase_session"], DEV_MODE)
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



# [추가] 로그인 안 되어 있으면 여기서 멈춤
if not st.session_state.get("supabase_session"):
    show_login(SUPABASE_URL, SUPABASE_ANON_KEY, DEV_MODE)
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
st.title("📈 AI 주식 페이스메이커")

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

with tab1:
    render_diary_tab(supabase, ai_client, DEV_MODE)
with tab2:
    render_records_tab(supabase)
with tab3:
    render_settings_tab(supabase)
