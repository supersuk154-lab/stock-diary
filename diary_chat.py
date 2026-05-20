import html as _html
import time
import streamlit as st
from google.genai import types
from ai_helper import safe_generate
from db import get_past_context
from app_constants import (
    TAG_SALARY_BUY, TAG_DIVIDEND, TAG_PRAISE_PAST,
    TAG_HOLD, TAG_DIDNT_CHECK, TAG_TAKE_BREAK,
    TAG_SHAKY, TAG_IMPULSE_TRADE, TAG_MISTAKE, PRIMARY_MODEL_NAME
)

MODEL_NAME = PRIMARY_MODEL_NAME


# ── 공통 AI 헬퍼 ──────────────────────────────────────────────────────────

def _get_tone_instruction() -> str:
    chosen_mentor = st.session_state.get("chosen_mentor", "")
    if "심리 상담가" in chosen_mentor:
        return "심리 상담가처럼 매우 따뜻하고 부드러운 존댓말로, 사용자의 감정 자체를 어루만지듯 답하세요."
    elif "주식 찐친" in chosen_mentor:
        return "10년 지기 동네 친구처럼 편안한 반말로, 친근하고 유쾌하게 위로하면서 답하세요."
    elif "1타 강사" in chosen_mentor:
        return "깐깐한 일타 강사처럼 단호하고 팩트 위주의 존댓말로, 원칙 준수와 장기 투자의 중요성을 강조하세요."
    else:
        return "정중하고 깔끔한 존댓말로, 따뜻하면서도 객관적으로 답하세요."


def _build_system_prompt(
    diary_text: str,
    tags_str: str,
    history_text: str,
    tone: str,
    opening: bool = False,
) -> str:
    """AI 시스템 프롬프트 생성. opening=True 이면 일기 첫 인사 모드."""
    base = f"""당신은 장기 투자자의 멘탈을 지켜주는 AI 주식메이트이자, 산전수전을 다 겪은 노련한 실전 투자 코치입니다.
단순한 위로나 의미 없는 대화를 넘어, 사용자에게 '장기 투자에 대한 흔들림 없는 확신'을 심어주는 것이 당신의 최종 목표입니다.

오늘 사용자가 쓴 투자 일기:
{diary_text}

사용자가 선택한 오늘의 상태 태그: {tags_str if tags_str else "없음"}

[핵심 대화 원칙]
1. 황금 비율: 감정 공감(20%) + 통찰과 꿀팁(60%) + 행동 유도 질문(20%)의 비율로 대화하세요.
2. 꿀팁 자연스럽게 녹이기: 교장선생님처럼 훈계하지 말고, 대화 흐름 속에 인사이트를 툭 던지듯 부드럽게 전달하세요.
3. 상황별 맞춤 코칭 (태그 기반):
   - 불안/공포 태그(#오늘좀흔들, #뇌동매매반성): 시장의 노이즈를 무시하는 법, 역사적인 폭락장 이후의 회복 통계, "남들이 겁을 낼 때 욕심을 내라"는 워런 버핏 등 대가들의 위기 극복 철학을 알려주세요.
   - 루틴/보상 태그(#월급날정기매수, #배당금달달해): 복리의 마법, '수량 늘리기'의 위력, 배당 재투자가 만드는 스노우볼 효과의 수학적/실질적 이점을 칭찬과 함께 설명해주세요.
   - 인내/방어 태그(#존버는승리한다, #오늘은안봤다, #한템포쉬어가기): 수면제를 먹고 10년 뒤에 깨어나라는 앙드레 코스톨라니의 조언처럼, '아무것도 하지 않는 것'이 때로는 최고의 투자 기술임을 극찬해주세요.
4. 발전적인 마무리: 대화의 마지막은 단순한 안부 묻기가 아니라, 투자의 본질을 다시 생각하게 만드는 짧은 질문으로 끝내세요.

[말투 지시]
{tone}"""

    if opening:
        base += (
            "\n\n사용자가 오늘의 투자 일기를 방금 공유했습니다. "
            "일기 내용을 읽고 핵심 감정과 상황을 1~2줄로 짚어준 뒤, "
            "따뜻하게 대화를 시작해주세요. 너무 길지 않게 3~5문장으로 답하세요."
        )
    else:
        base += (
            f"\n\n[지금까지의 대화]\n{history_text}\n\n"
            "위 대화 흐름에 자연스럽게 이어지도록, 사용자의 가장 최근 메시지에 답해주세요."
        )

    return base


# ── 메인 렌더 함수 ──────────────────────────────────────────────────────────

def render_chat_section(supabase, ai_client) -> list:
    """일기 입력 → 태그 선택 → AI 대화 단계별 UI. 선택된 태그 리스트를 반환합니다."""

    # 단계 초기화: "write" → "chat"
    if "diary_step" not in st.session_state:
        st.session_state["diary_step"] = "write"

    step = st.session_state["diary_step"]

    # ═══════════════════════════════════════════════════════
    # STEP 1: 일기 작성
    # ═══════════════════════════════════════════════════════
    if step == "write":
        st.markdown("### 💬 오늘의 투자 일기")
        st.caption("오늘 투자하면서 어떤 생각이 들었나요? 자유롭게 적어보세요.")

        with st.form("diary_write_form", clear_on_submit=False):
            diary_text = st.text_area(
                "일기 내용",
                placeholder=(
                    "예) 오늘 시장이 꽤 흔들렸는데 매수 타이밍인지 고민됐어요. "
                    "그래도 정기매수 루틴은 지켰습니다. 길게 보자고 다짐했어요."
                ),
                height=180,
                key="diary_text_input",
                label_visibility="collapsed",
            )
            next_clicked = st.form_submit_button(
                "다음 → 태그 & AI 멘토와 대화",
                type="primary",
                use_container_width=True,
            )

        if next_clicked:
            if diary_text and diary_text.strip():
                st.session_state["diary_initial_text"] = diary_text.strip()
                st.session_state["diary_step"] = "chat"
                st.session_state["current_tags"] = []
                st.session_state["chat_messages"] = []
                st.session_state["chat_opening_needed"] = True
                st.rerun()
            else:
                st.warning("✏️ 오늘 하루를 조금이라도 적어주세요!")

        return []

    # ═══════════════════════════════════════════════════════
    # STEP 2: 태그 선택 + AI 대화
    # ═══════════════════════════════════════════════════════
    diary_text = st.session_state.get("diary_initial_text", "")

    # ── 작성한 일기 미리보기 ──────────────────────────────────
    preview = diary_text[:80] + ("..." if len(diary_text) > 80 else "")
    safe_preview = _html.escape(preview)
    st.markdown(
        f'<div style="background:#F2F4F6; border-radius:10px; padding:10px 14px; '
        f'border-left:3px solid #3182F6; font-size:0.88em; color:#4E5968; '
        f'line-height:1.5; margin-bottom:6px;">📝 {safe_preview}</div>',
        unsafe_allow_html=True,
    )

    col_edit, col_new = st.columns(2)
    with col_edit:
        if st.button("✏️ 일기 수정", use_container_width=True, key="edit_diary_btn"):
            st.session_state["diary_step"] = "write"
            # 기존 텍스트 복원 (수정 시 다시 편집 가능)
            st.session_state["diary_text_input"] = diary_text
            st.session_state["chat_messages"] = []
            st.rerun()
    with col_new:
        if st.button("🆕 새 일기 작성", use_container_width=True, key="new_diary_btn"):
            st.session_state["diary_step"] = "write"
            st.session_state["diary_initial_text"] = ""
            st.session_state["diary_text_input"] = ""
            st.session_state["chat_messages"] = []
            st.session_state["current_tags"] = []
            # 태그 위젯 상태 초기화
            for _k in ("pills_routine", "pills_defense", "pills_emotion"):
                st.session_state.pop(_k, None)
            st.rerun()

    st.markdown("<div style='margin:4px 0'></div>", unsafe_allow_html=True)

    # ── 태그 선택 (접힌 상태로 시작 — 선택사항) ─────────────────
    with st.expander("🏷️ 오늘의 상태 태그 추가 (선택)", expanded=False):
        st.caption("🏃‍♂️ 나의 투자 루틴 (가점)")
        routine_tags = st.pills(
            "루틴",
            [TAG_SALARY_BUY, TAG_DIVIDEND, TAG_PRAISE_PAST],
            label_visibility="collapsed",
            selection_mode="multi",
            key="pills_routine",
        )
        st.caption("🛡️ 멘탈 방어 성공 (가점)")
        defense_tags = st.pills(
            "방어",
            [TAG_HOLD, TAG_DIDNT_CHECK, TAG_TAKE_BREAK],
            label_visibility="collapsed",
            selection_mode="multi",
            key="pills_defense",
        )
        st.caption("🚨 감정 및 반성 (AI 멘토링)")
        emotion_tags = st.pills(
            "감정",
            [TAG_SHAKY, TAG_IMPULSE_TRADE, TAG_MISTAKE],
            label_visibility="collapsed",
            selection_mode="multi",
            key="pills_emotion",
        )

    selected_tags = (routine_tags or []) + (defense_tags or []) + (emotion_tags or [])

    # 태그 변경 시 대화 리셋 + 재오프닝
    if selected_tags != st.session_state.get("current_tags", []):
        st.session_state["current_tags"] = selected_tags
        st.session_state["chat_messages"] = []
        st.session_state["chat_opening_needed"] = True
        st.rerun()

    # ── AI 멘토 대화 ──────────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 AI 멘토와 대화")

    _hint_mentor = st.session_state.get("chosen_mentor", "")
    if _hint_mentor:
        st.markdown(
            f'<div style="font-size:0.82em; color:#8B95A1; margin-bottom:4px;">'
            f'💬 <b>{_hint_mentor}</b>와 대화 중</div>',
            unsafe_allow_html=True,
        )

    # AI 오프닝 메시지: 일기 내용 읽고 첫 말걸기 (1회만 실행)
    if st.session_state.get("chat_opening_needed"):
        if not st.session_state.get("chosen_mentor"):
            st.info("👈 사이드바에서 멘토를 선택하면 AI가 일기를 읽고 먼저 말을 걸어줍니다.")
        else:
            with st.spinner("AI 멘토가 일기를 읽고 있습니다..."):
                tags_str = ", ".join(selected_tags) if selected_tags else ""
                tone = _get_tone_instruction()
                system_prompt = _build_system_prompt(
                    diary_text, tags_str, "", tone, opening=True
                )
                past_ctx = get_past_context(
                    selected_tags, supabase, st.session_state.get("user_id", "")
                )
                if past_ctx:
                    system_prompt += f"\n\n{past_ctx}"

                config = types.GenerateContentConfig(system_instruction=system_prompt)
                opening_text, err = safe_generate(
                    client=ai_client,
                    model_name=MODEL_NAME,
                    contents="(일기 내용을 읽고 첫 인사를 해주세요)",
                    config=config,
                    fallback_msg="안녕하세요! 오늘 일기를 써주셨군요. 편하게 이야기해 주세요. 🙏",
                )
                if err:
                    opening_text = "안녕하세요! 오늘 일기를 써주셨군요. 어떤 이야기든 편하게 들려주세요. 🙏"

            st.session_state["chat_messages"] = [
                {"role": "assistant", "content": opening_text}
            ]
            st.session_state["chat_opening_needed"] = False
            st.rerun()

    # 대화 히스토리
    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.get("chat_messages", []):
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    # 채팅 입력 폼
    with st.form("mind_chat_form", clear_on_submit=True):
        _mentor_label = st.session_state.get("chosen_mentor", "AI 멘토")
        user_input = st.text_area(
            "💭 추가로 하고 싶은 이야기",
            placeholder=f"{_mentor_label}에게 더 이야기해 보세요...",
            height=100,
            key="mind_chat_input",
        )
        col_send, col_clear = st.columns([7, 3])
        with col_send:
            send_clicked = st.form_submit_button(
                "보내기", type="primary", use_container_width=True
            )
        with col_clear:
            clear_clicked = st.form_submit_button("대화 초기화", use_container_width=True)

    if clear_clicked:
        st.session_state["chat_messages"] = []
        st.session_state["chat_opening_needed"] = True
        st.rerun()

    if send_clicked and user_input and user_input.strip():
        # [보안점검 #7] AI API 호출 속도 제한 (3초 쿨다운)
        last_call = st.session_state.get("last_ai_call", 0.0)
        if time.time() - last_call < 3.0:
            st.warning(
                "⚠️ 너무 빠른 속도로 메시지를 보내고 있습니다. 잠시 후 다시 시도해 주세요 (3초 제한)."
            )
            st.stop()
        st.session_state["last_ai_call"] = time.time()

        st.session_state["chat_messages"].append(
            {"role": "user", "content": user_input.strip()}
        )

        with st.spinner("AI 멘토가 답변을 고민 중입니다..."):
            tags_str = ", ".join(selected_tags) if selected_tags else ""
            tone = _get_tone_instruction()
            recent_history = st.session_state["chat_messages"][-8:]
            history_text = "\n".join([
                f"{'사용자' if m['role'] == 'user' else 'AI 멘토'}: {m['content']}"
                for m in recent_history
            ])
            system_prompt = _build_system_prompt(
                diary_text, tags_str, history_text, tone, opening=False
            )
            past_ctx = get_past_context(
                selected_tags, supabase, st.session_state.get("user_id", "")
            )
            if past_ctx:
                system_prompt += f"\n\n{past_ctx}"

            config = types.GenerateContentConfig(system_instruction=system_prompt)
            response_text, err = safe_generate(
                client=ai_client,
                model_name=MODEL_NAME,
                contents=user_input.strip(),
                config=config,
                fallback_msg="답변 생성 중 오류가 발생했어요.",
            )
            if err:
                response_text = (
                    "죄송해요, AI 서버가 잠시 바쁜 것 같아요. 잠시 후 다시 보내주세요. 🙏"
                )

        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": response_text}
        )
        st.rerun()

    return selected_tags
