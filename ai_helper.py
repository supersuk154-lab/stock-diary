import logging

logger = logging.getLogger(__name__)


def safe_generate(model, content, fallback_msg="AI 분석 중 오류가 발생했어요."):
    """Gemini API 호출 안전망."""
    try:
        response = model.generate_content(content)
        if not response.candidates or not getattr(response, 'text', None):
            return None, "⚠️ AI가 응답을 만들 수 없었어요. (안전 필터에 걸렸거나 빈 응답)"
        return response.text, None
    except Exception:
        logger.exception("Gemini call failed")
        return None, f"⚠️ {fallback_msg}"
