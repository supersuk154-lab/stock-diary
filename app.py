import streamlit as st
import streamlit.components.v1 as components
import logging
import base64
# [수정] 새로운 google-genai SDK 임포트
from google import genai
from google.genai import types
import os
import json
import re
import math
import datetime
from app_constants import KST
from pathlib import Path
import yfinance as yf
from session_utils import (
    SESSION_CACHE_PATH, get_dev_mode,
    save_session_to_disk, load_session_from_disk, clear_session_from_disk,
    clear_pin_cache,
)
from auth import show_login

# ==========================================
from tab_diary import render_diary_tab
from tab_records import render_records_tab
from tab_settings import render_settings_tab
from tab_report import render_report_tab
# [변경] 이미지 처리 라이브러리는 그대로
from PIL import Image, ImageDraw

# [변경] sqlite3 → supabase
from supabase import create_client, Client


def setup_pwa_assets():
    """Streamlit 내부 static 폴더에 PWA 파일들을 복사하고 index.html을 패치하여 PWA 설치를 완벽 지원합니다."""
    import shutil
    import re as _re
    from pathlib import Path

    try:
        st_static_dir = Path(st.__file__).parent / "static"
        if not st_static_dir.exists():
            return

        local_static_dir = Path(__file__).parent / "static"
        if not local_static_dir.exists():
            return

        # 1. manifest.json 복사 (Streamlit 기본 manifest 덮어쓰기)
        manifest_src = local_static_dir / "manifest.json"
        if manifest_src.exists():
            shutil.copy2(manifest_src, st_static_dir / "manifest.json")

        # 2. 아이콘 생성: icon.png → icon_192.png / icon_512.png (Pillow로 리사이즈)
        icon_src = local_static_dir / "icon.png"
        if icon_src.exists():
            from PIL import Image as _Image
            with _Image.open(icon_src) as _img:
                for _size, _name in [(192, "icon_192.png"), (512, "icon_512.png")]:
                    _dst = st_static_dir / _name
                    _resized = _img.resize((_size, _size), _Image.LANCZOS)
                    _resized.save(_dst, "PNG")

        # 3. sw.js (서비스 워커) 생성
        sw_content = """// sw.js — 최소 서비스 워커 (PWA 설치 요건 충족)
self.addEventListener('install', function(e) { self.skipWaiting(); });
self.addEventListener('activate', function(e) { return self.clients.claim(); });
self.addEventListener('fetch', function(e) {});
"""
        with open(st_static_dir / "sw.js", "w", encoding="utf-8") as f:
            f.write(sw_content)

        # 4. index.html 패치
        index_path = st_static_dir / "index.html"
        if not index_path.exists():
            return

        with open(index_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # 중복 패치 방지
        if "navigator.serviceWorker.register" not in html_content:
            # Streamlit 기본 manifest 링크 제거 → 우리 것이 유일하게 적용되도록
            html_content = _re.sub(
                r'<link[^>]+rel=["\']manifest["\'][^>]*/?>',
                '',
                html_content,
                flags=_re.IGNORECASE,
            )

            pwa_patch = """
  <!-- ▼ PWA 커스텀 설정 (주식메이트) ▼ -->
  <link rel="manifest" href="/manifest.json?v=3">
  <link rel="apple-touch-icon" href="/icon_192.png?v=3">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="주식메이트">
  <script>
    // ① 서비스 워커 등록
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js?v=3', { scope: '/' })
          .catch(function(e) { console.log('SW 등록 실패:', e); });
      });
    }
    // ② PIN 입력창 숫자 키패드 활성화 (삼성 인터넷 포함)
    //    components.html() iframe이 아닌 메인 문서에서 직접 실행하므로 크로스프레임 차단 없음
    (function() {
      function patchPinInputs() {
        document.querySelectorAll('input[type="password"]').forEach(function(el) {
          var ph = el.getAttribute('placeholder') || '';
          if (ph.includes('4자리') || ph.includes('0000')) {
            el.setAttribute('inputmode', 'numeric');
            el.setAttribute('pattern', '[0-9]*');
          }
        });
      }
      document.addEventListener('DOMContentLoaded', function() {
        new MutationObserver(patchPinInputs)
          .observe(document.body, { childList: true, subtree: true });
        patchPinInputs();
      });
    })();
  </script>
  <!-- ▲ PWA 커스텀 설정 끝 ▲ -->
</head>"""
            html_content = html_content.replace("</head>", pwa_patch)
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html_content)

    except Exception as e:
        import logging
        logging.warning(f"PWA 자산 자동 설정 실패: {e}")

# PWA 자산 설정 실행
setup_pwa_assets()


# ==========================================
# 2. 앱 기본 설정
# static/ 우선, assets/ 폴백으로 아이콘 탐색
_icon_path = Path(__file__).parent / "static" / "icon.png"
_icon_fallback = Path(__file__).parent / "assets" / "icon.png"
if not _icon_path.exists() and _icon_fallback.exists():
    _icon_path = _icon_fallback

if _icon_path.exists():
    _pil_icon = Image.open(_icon_path)
    st.set_page_config(page_title="AI 주식메이트", page_icon=_pil_icon, layout="centered")
else:
    st.set_page_config(page_title="AI 주식메이트", page_icon="📈", layout="centered")

# Streamlit 기본 메뉴, 푸터, 상단 헤더 데코레이션 숨기기 (Toss 스타일 앱 브랜딩 최적화, 단 모바일 사이드바 버튼은 유지)
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stDecoration"] { display: none !important; }
    button[data-testid="stHeaderDeploymentButton"] { display: none !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    /* 모바일 브라우저 주소창 스크롤 시 여백 최적화 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# PWA 연동은 서버 사이드 index.html 패치를 통해 실행됩니다.

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
<link rel="preload" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css" />
<style>
    /* 1. 폰트 변경 (Pretendard 적용) */
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif !important;
    }

    /* [최적화] 제목 옆 자동 생성되는 링크 아이콘 숨기기 */
    .stMarkdown a.header-anchor {
        display: none !important;
    }

    /* [최적화] 단어 중간에서 줄바꿈 방지 (한국어 가독성 최적화) */
    html, body, [class*="css"], .stMarkdown p, h1, h2, h3, h4, h5, h6 {
        word-break: keep-all !important;
        overflow-wrap: break-word !important;
    }

    /* 모바일 최소 글자 크기 보장 */
    .stMarkdown p, .stMarkdown li, .stCaption {
        font-size: 14px !important;
        line-height: 1.6 !important;
    }
    small, .stCaption > div {
        font-size: 13px !important;
    }

    /* 2. 전체 배경색 및 텍스트 색상 (밝고 깔끔하게) */
    .stApp {
        background-color: #F9FAFB; /* 아주 연한 회색 배경 */
        color: #191F28; /* 너무 까맣지 않은 부드러운 검정 텍스트 */
    }

    /* 3. 불필요한 기본 UI 숨기기 (진짜 앱처럼, 단 모바일 사이드바 토글은 유지) */
    #MainMenu {visibility: hidden;} /* 우측 상단 햄버거 메뉴 숨김 */
    footer {visibility: hidden;}    /* 하단 Streamlit 워터마크 숨김 */
    [data-testid="stDecoration"] { display: none !important; }
    button[data-testid="stHeaderDeploymentButton"] { display: none !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    
    /* 4. 버튼 디자인 (메인 / 보조 분리 및 터치 영역 확대) */
    button {
        min-height: 44px !important;
    }
    
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
    button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover,
    button[kind="primary"]:active, button[kind="primaryFormSubmit"]:active {
        background-color: #1B64DA !important; /* 마우스 오버 시 짙어짐 */
        transform: translateY(1px) !important;
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
    button[kind="secondary"]:hover, button[kind="secondaryFormSubmit"]:hover,
    button[kind="secondary"]:active, button[kind="secondaryFormSubmit"]:active {
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

    /* 구분선 연하게 */
    hr {
        border: none !important;
        border-top: 1px solid #F2F4F6 !important;
        margin: 20px 0 !important;
    }

    /* 탭(Bottom Nav 스타일) 최적화 */
    div[data-testid="stTabs"] button[data-baseweb="tab"] {
        flex: 1;
        text-align: center;
        padding: 12px 0;
    }

    /* Toast 위치 중앙 상단 */
    div[data-testid="stToastContainer"] {
        top: 5% !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        right: auto !important;
        bottom: auto !important;
    }
    div[data-testid="stToast"] {
        border-radius: 20px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
    }

    /* 7. 모바일 뷰 여백 최적화 및 iOS Safe Area */
    .block-container {
        padding-top: max(2rem, env(safe-area-inset-top)) !important; 
        padding-bottom: max(4rem, env(safe-area-inset-bottom)) !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 600px !important; /* 모바일 앱처럼 폭을 제한 */
    }

    /* [최적화] 모바일 기기 특화 스타일 (화면 폭 600px 이하) */
    @media (max-width: 600px) {
        /* 메인 타이틀 (h1) */
        .stMarkdown h1, h1 {
            font-size: 1.5rem !important;
            letter-spacing: -0.5px !important;
            word-break: keep-all !important;
            line-height: 1.3 !important;
        }

        /* 서브 타이틀 (h2) */
        .stMarkdown h2, h2 {
            font-size: 1.25rem !important;
            letter-spacing: -0.3px !important;
            word-break: keep-all !important;
        }

        /* 소제목 (h3) */
        .stMarkdown h3, h3 {
            font-size: 1.1rem !important;
            word-break: keep-all !important;
        }

        /* 본문 패딩 축소 */
        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }

        /* 탭 버튼 텍스트 크기 */
        div[data-testid="stTabs"] button[data-baseweb="tab"] {
            font-size: 0.85rem !important;
            padding: 10px 4px !important;
        }

        /* 업로더 텍스트 크기 줄이기 */
        [data-testid="stFileUploader"] label {
            font-size: 0.9rem !important;
        }
    }
</style>
"""
st.markdown(toss_style, unsafe_allow_html=True)
# ---------------------------------------------------------

from app_constants import PRIMARY_MODEL_NAME
MODEL_NAME = PRIMARY_MODEL_NAME

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
    logging.exception("secrets 로드 실패")
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
                # pyrefly: ignore [missing-attribute]
                st.session_state["user_id"] = _resp.user.id
                # pyrefly: ignore [missing-attribute]
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
@st.cache_resource
def _get_supabase_client() -> Client:
    """Supabase 클라이언트 인스턴스를 캐싱하여 재사용합니다."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_supabase() -> Client:
    """현재 로그인된 사용자의 세션을 가진 Supabase 클라이언트 반환."""
    # [수정 #8] 매번 새 클라이언트를 생성하지 않고 캐싱된 인스턴스 재사용
    client = _get_supabase_client()

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
st.title("📈 AI 주식메이트")
st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

# [추가] 사이드바 상단에 로그인 정보 + 로그아웃 버튼
st.sidebar.markdown(f"👤 **{st.session_state.get('user_email', '로그인됨')}**")
if DEV_MODE:
    st.sidebar.caption("🛠️ 개발 모드 — 세션 자동 유지 중")
if st.sidebar.button("🚪 로그아웃"):
    # [수정 #14] 작업 중인 데이터가 있으면 경고
    has_unsaved = (
        st.session_state.get('daily_stock_list')
        or st.session_state.get('current_step', 'upload_mode') != 'upload_mode'
    )
    if has_unsaved and not st.session_state.get('_logout_confirmed'):
        st.session_state['_logout_confirmed'] = True
        st.sidebar.warning("⚠️ 입력 중인 데이터가 있습니다! 다시 한번 로그아웃 버튼을 누르면 진행합니다.")
        st.stop()
    clear_session_from_disk()
    clear_pin_cache()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["📝 일기 작성", "📚 과거 기록 조회", "📰 투자 리포트", "⚙️ 설정 및 백업"])

with tab1:
    render_diary_tab(supabase, ai_client, DEV_MODE)
with tab2:
    render_records_tab(supabase)
with tab3:
    render_report_tab(supabase, st.secrets)
with tab4:
    render_settings_tab(supabase, ai_client=ai_client, model_name=MODEL_NAME, dev_mode=DEV_MODE)
