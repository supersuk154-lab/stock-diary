import json
import os
import hashlib
from pathlib import Path

SESSION_CACHE_PATH = Path(".streamlit") / "session_cache.json"
PIN_CACHE_PATH = Path(".streamlit") / "pin_cache.json"


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


def save_pin_cache(session_dict: dict, pin_hash: str, email: str) -> None:
    """PIN 해시 + 세션 토큰을 pin_cache.json에 저장."""
    try:
        PIN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"pin_hash": pin_hash, "email": email, **session_dict}
        PIN_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def load_pin_cache() -> dict | None:
    """PIN 캐시 읽기. 없거나 손상되면 None 반환."""
    try:
        if PIN_CACHE_PATH.exists():
            return json.loads(PIN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def clear_pin_cache() -> None:
    """PIN 캐시 파일 삭제."""
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
