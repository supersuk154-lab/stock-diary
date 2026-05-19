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
                send_clicked = st.form_submit_button("💌 AI 멘토에게 보내기", type="primary", width="stretch")
            with col_clear:
                clear_clicked = st.form_submit_button("🔄 대화 초기화", width="stretch")
    
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
    
                system_instruction = f"""당신은 장기 투자자의 멘탈을 지켜주는 AI 페이스메이커이자, 산전수전을 다 겪은 노련한 실전 투자 코치입니다.
단순한 위로나 의미 없는 대화를 넘어, 사용자에게 '장기 투자에 대한 흔들림 없는 확신'을 심어주는 것이 당신의 최종 목표입니다.

사용자가 오늘 선택한 감정/상태 태그: {tags_str}

[핵심 대화 원칙]
1. 황금 비율: 감정 공감(20%) + 통찰과 꿀팁(60%) + 행동 유도 질문(20%)의 비율로 대화하세요.
2. 꿀팁 자연스럽게 녹이기: 교장선생님처럼 훈계하지 말고, 대화 흐름 속에 인사이트를 툭 던지듯 부드럽게 전달하세요.
3. 상황별 맞춤 코칭 (태그 기반):
   - 불안/공포 태그(#오늘좀흔들, #뇌동매매반성): 시장의 노이즈를 무시하는 법, 역사적인 폭락장 이후의 회복 통계, "남들이 겁을 낼 때 욕심을 내라"는 워런 버핏 등 대가들의 위기 극복 철학을 알려주세요.
   - 루틴/보상 태그(#월급날정기매수, #배당금달달해): 복리의 마법, '수량 늘리기'의 위력, 배당 재투자가 만드는 스노우볼 효과의 수학적/실질적 이점을 칭찬과 함께 설명해주세요.
   - 인내/방어 태그(#존버는승리한다, #오늘은안봤다, #한템포쉬어가기): 수면제를 먹고 10년 뒤에 깨어나라는 앙드레 코스톨라니의 조언처럼, '아무것도 하지 않는 것'이 때로는 최고의 투자 기술임을 극찬해주세요.
4. 발전적인 마무리: 대화의 마지막은 단순한 안부 묻기가 아니라, 투자의 본질을 다시 생각하게 만드는 짧은 질문으로 끝내세요. (예: "이 종목을 처음 모아가기로 결심했던 가장 큰 이유는 무엇이었나요?", "이번 배당금은 어디에 다시 씨앗으로 뿌릴 계획이신가요?")

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
