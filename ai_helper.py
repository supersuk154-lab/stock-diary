import json
import re
import time
import logging
from google import genai
from google.genai import types
from app_constants import FALLBACK_MODEL_NAME

logger = logging.getLogger(__name__)

def safe_generate(client, model_name, contents, config=None, fallback_msg="AI 분석 중 오류가 발생했어요."):
    """새로운 google-genai SDK 규격에 맞춘 안전망 함수.
    - 503 UNAVAILABLE: 최대 3회 재시도 (3초 간격)
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

            # 503: 일시적 과부하 → 재시도
            if is_503 and attempt < max_retries - 1:
                wait = 3 * (attempt + 1)
                logger.warning(f"503 UNAVAILABLE (attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
                time.sleep(wait)
                continue

            # 429 또는 재시도 소진된 503: 폴백 모델 시도
            if (is_429 or is_503) and model_name != FALLBACK_MODEL_NAME:
                reason = "503 과부하" if is_503 else "429 할당량 초과"
                logger.info(f"{reason} — {FALLBACK_MODEL_NAME}으로 자동 폴백 시도...")
                try:
                    response = client.models.generate_content(
                        model=FALLBACK_MODEL_NAME,
                        contents=contents,
                        config=config
                    )
                    if not response.text:
                        return None, "⚠️ AI가 응답을 만들 수 없었어요. (폴백 모델 빈 응답)"
                    return response.text, None
                except Exception as fallback_err:
                    logger.exception(f"폴백 모델 {FALLBACK_MODEL_NAME}도 실패")
                    return None, (
                        f"⚠️ {fallback_msg}\n\n"
                        f"기본 모델({model_name})과 폴백 모델({FALLBACK_MODEL_NAME}) 모두 응답하지 않습니다.\n"
                        f"잠시 후 다시 시도해 주세요.\n\n오류: {fallback_err}"
                    )

            logger.exception(f"Gemini call failed (attempt {attempt+1})")
            return None, f"⚠️ {fallback_msg}\n\n잠시 후 다시 시도해 주세요.\n\n오류 내용: {e}"


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
