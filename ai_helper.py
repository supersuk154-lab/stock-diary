import logging
from google import genai
from google.genai import types
from constants import FALLBACK_MODEL_NAME

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
