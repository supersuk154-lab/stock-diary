import json
import re
import logging
from google import genai
from google.genai import types
from app_constants import FALLBACK_MODEL_NAME

logger = logging.getLogger(__name__)

def safe_generate(client, model_name, contents, config=None, fallback_msg="AI 분석 중 오류가 발생했어요."):
    """새로운 google-genai SDK 규격에 맞춘 안전망 함수 + 429 한도 초과 시 FALLBACK_MODEL_NAME 자동 폴백"""
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
        logger.warning(f"Gemini call failed with model {model_name}: {e}")
        
        # 429 또는 RESOURCE_EXHAUSTED 한도 도달 시 FALLBACK_MODEL_NAME 자동 폴백 시도
        is_429 = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "quota" in str(e).lower()
        if is_429 and model_name != FALLBACK_MODEL_NAME:
            logger.info(f"Attempting automatic fallback to {FALLBACK_MODEL_NAME} due to quota/429 error...")
            try:
                response = client.models.generate_content(
                    model=FALLBACK_MODEL_NAME,
                    contents=contents,
                    config=config
                )
                if not response.text:
                    return None, "⚠️ AI가 응답을 만들 수 없었어요. (폴백 모델에서 안전 필터에 걸렸거나 빈 응답)"
                return response.text, None
            except Exception as fallback_err:
                logger.exception(f"Fallback to {FALLBACK_MODEL_NAME} also failed")
                return None, f"⚠️ {fallback_msg}\n\n[폴백 실패] {fallback_err}\n\nAPI 키가 올바른 프로젝트에 연결되어 있는지 확인해 주세요."
        
        logger.exception("Gemini call failed")
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
