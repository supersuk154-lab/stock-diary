import streamlit as st
from google.genai import types
from ai_helper import safe_generate
from db import get_past_context
from constants import (
    TAG_SALARY_BUY, TAG_DIVIDEND, TAG_PRAISE_PAST,
    TAG_HOLD, TAG_DIDNT_CHECK, TAG_TAKE_BREAK,
    TAG_SHAKY, TAG_IMPULSE_TRADE, TAG_MISTAKE
)

MODEL_NAME = "gemini-3.1-flash-lite"

def render_chat_section(supabase, ai_client) -> list:
    """태그 선택 UI 및 AI 멘토와의 자유 대화 섹션을 렌더링하고, 선택된 태그 리스트를 반환합니다."""
    st.markdown("### 🏷️ 오늘의 상태 (터치해서 선택)")
    
    st.caption("🏃‍♂️ 나의 투자 루틴 (가점)")
    routine_tags = st.pills(
        "루틴", 
        [TAG_SALARY_BUY, TAG_DIVIDEND, TAG_PRAISE_PAST],
        label_visibility="collapsed", 
        selection_mode="multi"
    )
    
    st.caption("🛡️ 멘탈 방어 성공 (가점)")
    defense_tags = st.pills(
        "방어", 
        [TAG_HOLD, TAG_DIDNT_CHECK, TAG_TAKE_BREAK],
        label_visibility="collapsed", 
        selection_mode="multi"
    )
    
    st.caption("🚨 감정 및 반성 (AI 멘토링)")
    emotion_tags = st.pills(
        "감정", 
        [TAG_SHAKY, TAG_IMPULSE_TRADE, TAG_MISTAKE],
        label_visibility="collapsed", 
        selection_mode="multi"
    )
    
    selected_tags = (routine_tags or []) + (defense_tags or []) + (emotion_tags or [])
    
    # 태그 변경 시 채팅 초기화
    if selected_tags != st.session_state.get('current_tags', []):
        st.session_state['current_tags'] = selected_tags
        if selected_tags:
            tags_str = ", ".join(selected_tags)
            st.session_state['chat_messages'] = [
                {
                    "role": "assistant",
                    "content": f"선택하신 **{tags_str}** 태그에 대해 이야기해 볼까요? 오늘 어떤 생각으로 이 상태를 고르셨는지 편하게 들려주세요."
                }
            ]
        else:
            st.session_state['chat_messages'] = []
        st.rerun()
    
    st.markdown("---")
    st.subheader("💬 지금 내 마음 상태 이야기하기")
    
    if not selected_tags:
        st.info("👆 위에서 마음에 맞는 태그를 **1개 이상** 골라주세요. 그러면 아래에 AI 멘토와 대화할 수 있는 창이 열립니다.")
    else:
        st.caption("선택한 태그를 보고 AI 멘토가 먼저 말을 걸어줍니다. 자유롭게 답하면서 마음을 정리해보세요.")
    
        # 1) 대화 히스토리 표시 (입력창 위에 누적, 스크롤 컨테이너 적용)
        chat_container = st.container(height=350)
        with chat_container:
            for msg in st.session_state.get('chat_messages', []):
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])
    
        # 2) 인라인 입력 폼
        with st.form("mind_chat_form", clear_on_submit=True):
            user_input = st.text_area(
                "💭 지금 내 심정을 자유롭게 적어보세요",
                placeholder="예) 시장이 흔들려서 마음이 너무 불안해요. 그냥 다 팔아버리고 싶은데 어떡하죠?",
                height=110,
                key="mind_chat_input",
            )
            col_send, col_clear = st.columns([7, 3])
            with col_send:
                send_clicked = st.form_submit_button("💌 AI 멘토에게 보내기", type="primary", use_container_width=True)
            with col_clear:
                clear_clicked = st.form_submit_button("🔄 대화 초기화", use_container_width=True)
    
        if clear_clicked:
            tags_str = ", ".join(selected_tags)
            st.session_state['chat_messages'] = [
                {
                    "role": "assistant",
                    "content": f"선택하신 **{tags_str}** 태그에 대해 다시 이야기해 볼까요? 오늘 어떤 생각이 드는지 편하게 들려주세요."
                }
            ]
            st.rerun()
    
        if send_clicked and user_input and user_input.strip():
            # [보안점검 #7] AI API 호출 속도 제한 (3초 쿨다운)
            import time
            last_call = st.session_state.get("last_ai_call", 0.0)
            if time.time() - last_call < 3.0:
                st.warning("⚠️ 너무 빠른 속도로 메시지를 보내고 있습니다. 잠시 후 다시 시도해 주세요 (3초 제한).")
                st.stop()
            st.session_state["last_ai_call"] = time.time()

            # 사용자 메시지 저장
            st.session_state['chat_messages'].append(
                {"role": "user", "content": user_input.strip()}
            )
    
            # AI 응답 생성
            with st.spinner("AI 멘토가 답변을 고민 중입니다..."):
                tags_str = ", ".join(selected_tags)
                chosen_mentor = st.session_state.get('chosen_mentor', '')
    
                tone_instruction = ""
                if "심리 상담가" in chosen_mentor:
                    tone_instruction = "심리 상담가처럼 매우 따뜻하고 부드러운 존댓말로, 사용자의 감정 자체를 어루만지듯 답하세요."
                elif "주식 찐친" in chosen_mentor:
                    tone_instruction = "10년 지기 동네 친구처럼 편안한 반말로, 친근하고 유쾌하게 위로하면서 답하세요."
                elif "1타 강사" in chosen_mentor:
                    tone_instruction = "깐깐한 일타 강사처럼 단호하고 팩트 위주의 존댓말로, 원칙 준수와 장기 투자의 중요성을 강조하세요."
                else:
                    tone_instruction = "정중하고 깔끔한 존댓말로, 따뜻하면서도 객관적으로 답하세요."
    
                recent_history = st.session_state['chat_messages'][-8:]
                history_text = "\n".join([
                    f"{'사용자' if m['role']=='user' else 'AI 멘토'}: {m['content']}"
                    for m in recent_history
                ])
    
                system_instruction = f"""당신은 장기 투자자의 멘탈을 지켜주는 AI 페이스메이커입니다.
사용자가 오늘 선택한 감정/상태 태그: {tags_str}

[원칙]
- 감정은 무죄, 충동적 행동(매도)은 유죄. 사용자의 감정을 비난하지 말고 행동을 막는 데 집중하세요.
- 짧고 친근하게, 1~3 문단 정도로 답하세요.
- 마지막엔 짧은 후속 질문 하나로 대화를 이어주세요.

[말투 지시]
{tone_instruction}

[지금까지의 대화]
{history_text}

위 대화 흐름에 자연스럽게 이어지도록, 사용자의 가장 최근 메시지에 답해주세요."""
    
                # [수정] get_past_context에 st.session_state.get("user_id", "")를 전달하여 보안 강화
                past_context = get_past_context(selected_tags, supabase, st.session_state.get("user_id", ""))
                if past_context:
                    system_instruction += f"\n\n{past_context}"
    
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
                
                response_text, err = safe_generate(
                    client=ai_client,
                    model_name=MODEL_NAME,
                    contents=user_input.strip(),
                    config=config,
                    fallback_msg="답변 생성 중 오류가 발생했어요."
                )
    
                if err:
                    st.error(err)
                    response_text = "죄송해요, 잠시 답변을 만들지 못했어요. 잠시 후 다시 보내주세요."
    
                st.session_state['chat_messages'].append(
                    {"role": "assistant", "content": response_text}
                )
    
            st.rerun()

    return selected_tags
