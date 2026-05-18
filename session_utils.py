import json
import os
from pathlib import Path

SESSION_CACHE_PATH = Path(".streamlit") / "session_cache.json"


def get_dev_mode(secrets) -> bool:
    """Streamlit Cloud 환경에서는 자동으로 비활성화."""
    return (
        secrets.get("DEV_MODE", False)
        and not os.environ.get("STREAMLIT_SERVER_HEADLESS")
    )


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