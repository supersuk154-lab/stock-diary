import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

def safe_generate(client, model_name, contents, config=None, fallback_msg="AI 분석 중 오류가 발생했어요."):
    """새로운 google-genai SDK 규격에 맞춘 안전망 함수"""
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
        logger.exception("Gemini call failed")
        return None, f"⚠️ {fallback_msg}\n\n잠시 후 다시 시도해 주세요."
