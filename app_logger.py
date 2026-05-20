"""
앱 이벤트 로거 — Supabase app_logs 테이블에 영구 저장.
실패해도 앱 동작에 절대 영향 없도록 모든 예외를 흡수합니다.

사용법:
    from app_logger import log_event, timed_log

    # 단순 이벤트
    log_event("diary_save", "일기 저장 완료", extra={"tags": tags})

    # AI 호출 시간 측정 + 자동 로그
    with timed_log("ai_call", extra={"type": "chat"}):
        result = safe_generate(...)
"""
import time
import streamlit as st

# 모듈 레벨 클라이언트 — app.py 에서 init_logger() 로 등록
_client = None


def init_logger(supabase_client) -> None:
    """앱 시작 직후 한 번 호출해 Supabase 클라이언트를 등록합니다."""
    global _client
    _client = supabase_client


def log_event(
    event: str,
    message: str = "",
    level: str = "INFO",           # INFO / WARNING / ERROR
    user_id: str | None = None,
    extra: dict | None = None,
    supabase=None,                 # 직접 전달 (모듈 초기화 전 사용 가능)
) -> None:
    """app_logs 테이블에 이벤트를 기록합니다."""
    client = supabase or _client
    if client is None:
        return
    try:
        uid = user_id or st.session_state.get("user_id") or None
        client.table("app_logs").insert({
            "user_id": uid,
            "level": level,
            "event": event,
            "message": str(message)[:1000],
            "extra": extra or {},
        }).execute()
    except Exception:
        pass   # 로그 실패는 무음 처리 — 앱에 영향 없음


class _TimedLogContext:
    """AI 호출 등 실행시간 측정이 필요한 블록에 사용하는 컨텍스트 매니저."""
    def __init__(self, event: str, extra: dict, supabase, user_id):
        self.event = event
        self.extra = extra
        self._supabase = supabase
        self._user_id = user_id
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.perf_counter() - self._start) * 1000)
        lvl = "ERROR" if exc_type else "INFO"
        self.extra["latency_ms"] = elapsed_ms
        if exc_type:
            self.extra["error"] = str(exc_val)[:300]
        log_event(
            event=self.event,
            level=lvl,
            user_id=self._user_id,
            extra=self.extra,
            supabase=self._supabase,
        )
        return False  # 예외는 그대로 전파


def timed_log(
    event: str,
    extra: dict | None = None,
    supabase=None,
    user_id: str | None = None,
) -> _TimedLogContext:
    """with 블록 실행시간을 측정해 자동 로그를 남깁니다.

    Example:
        with timed_log("ai_chat", extra={"model": MODEL_NAME}):
            response, err = safe_generate(...)
    """
    return _TimedLogContext(event, extra or {}, supabase, user_id)
