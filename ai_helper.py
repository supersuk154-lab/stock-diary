import json
import re
import time
import logging
from google import genai
from google.genai import types
from app_constants import FALLBACK_MODEL_NAME

logger = logging.getLogger(__name__)


def _toast(msg: str, icon: str = "⏳"):
    """Streamlit 컨텍스트 안에서만 toast 알림 — 밖에서 호출돼도 무시."""
    try:
        import streamlit as st
        st.toast(msg, icon=icon)
    except Exception:
        pass


def safe_generate(client, model_name, contents, config=None, fallback_msg="AI 분석 중 오류가 발생했어요."):
    """새로운 google-genai SDK 규격에 맞춘 안전망 함수.
    - 503 UNAVAILABLE: 최대 3회 재시도 (대기 중 사용자에게 toast 알림)
    - 429 RESOURCE_EXHAUSTED: FALLBACK_MODEL_NAME으로 자동 폴백
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
            if not response.text:
                return None, "⚠️ AI가 응답을 만들 수 없었어요. (안전 필터에 걸렸거나 빈 응답)"
            return response.text, None

        except Exception as e:
            err_str = str(e)
            is_503 = "503" in err_str or "UNAVAILABLE" in err_str
            is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()

            # 503: 일시적 과부하 → 재시도 (사용자에게 대기 안내)
            if is_503 and attempt < max_retries - 1:
                wait = 3 * (attempt + 1)
                logger.warning(f"503 UNAVAILABLE (attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
                _toast(f"AI 서버가 잠시 바쁩니다 · {wait}초 후 자동으로 다시 시도합니다 ({attempt+1}/{max_retries-1})")
                time.sleep(wait)
                continue

            # 429 또는 재시도 소진된 503: 폴백 모델 시도
            if (is_429 or is_503) and model_name != FALLBACK_MODEL_NAME:
                reason = "503 과부하" if is_503 else "요청 한도 초과"
                logger.info(f"{reason} — {FALLBACK_MODEL_NAME}으로 자동 폴백 시도...")
                _toast("보조 AI 모델로 전환 중입니다 · 잠시만 기다려주세요", icon="🔄")
                try:
                    response = client.models.generate_content(
                        model=FALLBACK_MODEL_NAME,
                        contents=contents,
                        config=config
                    )
                    if not response.text:
                        return None, "⚠️ AI가 응답을 만들 수 없었어요. (안전 필터에 걸렸거나 빈 응답)"
                    return response.text, None
                except Exception as fallback_err:
                    logger.exception(f"폴백 모델 {FALLBACK_MODEL_NAME}도 실패")
                    return None, (
                        "⚠️ AI 서버가 일시적으로 응답하지 않습니다.\n\n"
                        "잠시 후 다시 시도해 주세요. 계속 반복되면 몇 분 뒤에 다시 접속해 보세요."
                    )

            logger.exception(f"Gemini call failed (attempt {attempt+1}): {e}")
            return None, f"⚠️ {fallback_msg}\n\n잠시 후 다시 시도해 주세요."


def ai_resolve_ticker(client, model_name: str, stock_name: str) -> str | None:
    """한글 종목명 등 자동 매칭 실패 시 AI로 야후파이낸스 티커를 조회.

    Returns: 티커 문자열(예: 'GOOGL', '005930.KS') 또는 None
    """
    prompt = (
        f'종목명: "{stock_name}"\n\n'
        "위 종목의 야후파이낸스(Yahoo Finance) 티커 심볼을 반환하시오.\n"
        "규칙:\n"
        "- 한국 KOSPI 상장 주식/ETF → '6자리숫자.KS' (예: 005930.KS, 069500.KS)\n"
        "- 한국 KOSDAQ 상장 주식/ETF → '6자리숫자.KQ' (예: 035420.KQ)\n"
        "- 미국 주식/ETF → 영문 티커 (예: AAPL, GOOGL, SPYG, JEPQ)\n"
        "- 한글 종목명이면 해당 종목의 KRX 코드를 찾아 위 형식으로 반환\n"
        "반드시 아래 JSON만 출력하고 다른 텍스트는 절대 포함하지 마시오:\n"
        '{"ticker": "005930.KS", "reason": "한 줄 근거"}\n'
        '확실하지 않으면: {"ticker": null, "reason": "이유"}'
    )
    try:
        config = types.GenerateContentConfig(
            system_instruction="당신은 한국·미국 주식 및 ETF 종목 데이터 전문가입니다. KRX 종목코드와 야후파이낸스 티커를 정확히 알고 있습니다. JSON만 출력합니다."
        )
        text, err = safe_generate(client, model_name, prompt, config=config)
        if err or not text:
            return None
        cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        data = json.loads(cleaned)
        ticker = data.get("ticker")
        return ticker.strip().upper() if ticker else None
    except Exception as e:
        logger.warning(f"ai_resolve_ticker 실패 ({stock_name}): {e}")
        return None


def normalize_stock_name(client, model_name: str, raw_input: str) -> dict:
    """사용자가 입력한 비정형 종목명을 AI로 정규화.

    Returns:
        {"name": str | None, "reason": str}
        name이 None이면 AI가 종목을 파악하지 못한 것.
    """
    prompt = (
        f'사용자가 입력한 주식 종목명: "{raw_input}"\n\n'
        "위 입력이 어떤 주식 종목을 가리키는지 파악하여 정식 종목명으로 변환하시오.\n"
        "한국 주식은 '종목명(티커)' 형식(예: 삼성전자(005930)), "
        "해외 주식은 영문 공식명칭과 티커(예: Schwab US Dividend Equity ETF (SCHD))으로 표기하시오.\n"
        "확실하지 않아도 가장 가능성 높은 종목 하나만 제시하시오.\n"
        "반드시 아래 JSON만 출력하고 다른 텍스트는 절대 포함하지 마시오:\n"
        '{"name": "정식종목명", "reason": "한 줄 근거"}\n'
        '전혀 파악 불가하면: {"name": null, "reason": "파악 불가 이유"}'
    )
    try:
        config = types.GenerateContentConfig(
            system_instruction="당신은 주식 종목명 데이터 정규화 전문가입니다. JSON만 출력합니다."
        )
        text, err = safe_generate(client, model_name, prompt, config=config)
        if err or not text:
            return {"name": None, "reason": "AI 호출에 실패했습니다."}

        cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        data = json.loads(cleaned)
        return {
            "name": data.get("name"),
            "reason": data.get("reason", ""),
        }
    except Exception as e:
        logger.warning(f"normalize_stock_name 실패: {e}")
        return {"name": None, "reason": f"오류: {e}"}
