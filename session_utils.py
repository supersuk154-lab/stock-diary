import json
import os
import base64
import hashlib
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

SESSION_CACHE_PATH = Path(".streamlit") / "session_cache.json"
PIN_CACHE_PATH     = Path(".streamlit") / "pin_cache.json"

# 브라우저 쿠키 설정 (서버 재시작·재배포에도 유지)
_COOKIE_NAME    = "pacemaker_pin_v1"
_COOKIE_MAX_AGE = 30 * 24 * 3600   # 30일


def get_dev_mode(secrets) -> bool:
    """Streamlit Cloud 환경에서는 자동으로 비활성화."""
    return (
        secrets.get("DEV_MODE", False)
        and not os.environ.get("STREAMLIT_SERVER_HEADLESS")
    )


# ── PIN 관련 유틸 ──────────────────────────────────────────

def hash_pin(pin: str) -> str:
    """PIN을 레인보우 테이블 공격 방어용 PEPPER와 함께 SHA-256으로 해싱."""
    PEPPER = "StockDiaryPacemaker2026!#@$"
    return hashlib.sha256((pin + PEPPER).encode('utf-8')).hexdigest()


def _cookie_js(value: str, max_age: int) -> str:
    """쿠키 설정 JavaScript 생성. window.parent로 메인 앱 프레임에 직접 설정."""
    cookie_str = f"{_COOKIE_NAME}={value}; max-age={max_age}; path=/; SameSite=Strict"
    return f"""
    <script>
    (function() {{
        var c = "{cookie_str}";
        try {{ window.parent.document.cookie = c; }} catch(e) {{}}
        try {{ document.cookie = c; }} catch(e) {{}}
    }})();
    </script>
    """


def _save_pin_to_cookie(data: dict) -> None:
    """PIN 데이터를 브라우저 쿠키에 저장 (30일 유지)."""
    try:
        encoded = base64.b64encode(
            json.dumps(data, ensure_ascii=False).encode()
        ).decode()
        components.html(_cookie_js(encoded, _COOKIE_MAX_AGE), height=0)
    except Exception:
        pass


def _load_pin_from_cookie() -> dict | None:
    """브라우저 쿠키에서 PIN 데이터 읽기 (st.context.cookies, Streamlit 1.37+)."""
    try:
        encoded = st.context.cookies.get(_COOKIE_NAME)
        if encoded:
            return json.loads(base64.b64decode(encoded.encode()).decode())
    except Exception:
        pass
    return None


def _clear_pin_cookie() -> None:
    """브라우저 쿠키에서 PIN 삭제."""
    try:
        components.html(_cookie_js("", 0), height=0)
    except Exception:
        pass


def save_pin_cache(session_dict: dict, pin_hash: str, email: str) -> None:
    """PIN 해시 + 세션 토큰을 브라우저 쿠키(우선) + 파일(폴백)에 저장."""
    data = {"pin_hash": pin_hash, "email": email, **session_dict}
    # ① 브라우저 쿠키 (재배포·재시작에도 유지됨)
    _save_pin_to_cookie(data)
    # ② 로컬 파일 (개발 환경 폴백)
    try:
        PIN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PIN_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def load_pin_cache() -> dict | None:
    """PIN 캐시 읽기. 브라우저 쿠키 우선, 없으면 파일, 둘 다 없으면 None."""
    # ① 브라우저 쿠키 (재배포 후에도 살아있음)
    cookie_data = _load_pin_from_cookie()
    if cookie_data and cookie_data.get("pin_hash") and cookie_data.get("access_token"):
        return cookie_data
    # ② 로컬 파일 폴백
    try:
        if PIN_CACHE_PATH.exists():
            return json.loads(PIN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def clear_pin_cache() -> None:
    """브라우저 쿠키 + 파일 모두 삭제."""
    _clear_pin_cookie()
    try:
        if PIN_CACHE_PATH.exists():
            PIN_CACHE_PATH.unlink()
    except Exception:
        pass


# ── DEV_MODE 세션 캐시 (기존) ────────────────────────────

def save_session_to_disk(session_dict: dict, dev_mode: bool) -> None:
    if not dev_mode:
        return
    try:
        SESSION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_CACHE_PATH.write_text(json.dumps(session_dict), encoding="utf-8")
    except Exception:
        pass


def load_session_from_disk(dev_mode: bool) -> dict | None:
    if not dev_mode:
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
