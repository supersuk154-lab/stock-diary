import json
import os
import base64
import hashlib
import secrets as _secrets
import streamlit as st
import streamlit.components.v1 as _components
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

def generate_pin_salt() -> str:
    """PIN 해시에 사용할 무작위 per-user salt 생성 (32자 hex)."""
    return _secrets.token_hex(16)


def hash_pin(pin: str, salt: str = "") -> str:
    """PIN을 SHA-256으로 해싱. PEPPER + per-user salt 적용.
    salt 없이 호출하면 기존 해시와 호환 (구버전 캐시 유지)."""
    PEPPER = "StockDiaryPacemaker2026!#@$"
    return hashlib.sha256((pin + PEPPER + salt).encode('utf-8')).hexdigest()


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
        _components.html(_cookie_js(encoded, _COOKIE_MAX_AGE), height=0)
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
        _components.html(_cookie_js("", 0), height=0)
    except Exception:
        pass


def save_pin_cache(
    session_dict: dict,
    pin_hash: str,
    email: str,
    pin_salt: str = "",
    dev_mode: bool = False,
) -> None:
    """PIN 해시 + 세션 토큰을 브라우저 쿠키(우선) + 파일(폴백)에 저장.
    파일 저장은 dev_mode 일 때만 — 프로덕션에서 토큰이 디스크에 남지 않도록."""
    data = {"pin_hash": pin_hash, "pin_salt": pin_salt, "email": email, **session_dict}
    # ① 브라우저 쿠키 (재배포·재시작에도 유지됨)
    _save_pin_to_cookie(data)
    # ② 로컬 파일 — 개발 환경 전용 (프로덕션에서는 비활성)
    if dev_mode:
        try:
            PIN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            PIN_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass


def save_pin_lockout(pin_data: dict, locked_until_iso: str) -> None:
    """PIN 연속 실패 잠금 상태를 쿠키에 덮어씀 (토큰·해시는 유지)."""
    updated = {**pin_data, "locked_until": locked_until_iso}
    _save_pin_to_cookie(updated)


def load_pin_cache() -> dict | None:
    """PIN 캐시 읽기. 브라우저 쿠키 우선, 없으면 파일, 둘 다 없으면 None.
    locked_until만 있는 쿠키(5회 실패 잠금 상태)도 반환해 잠금이 소실되지 않도록 한다."""
    # ① 브라우저 쿠키 (재배포 후에도 살아있음)
    cookie_data = _load_pin_from_cookie()
    if cookie_data and cookie_data.get("pin_hash"):
        # 토큰이 있거나 잠금 상태인 경우 모두 유효한 캐시로 처리
        if cookie_data.get("access_token") or cookie_data.get("locked_until"):
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
