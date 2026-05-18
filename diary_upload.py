import streamlit as st
import json
from PIL import Image, ImageDraw
from google.genai import types
from ai_helper import safe_generate
from prices import _market_time_bucket, get_realtime_prices_bulk, TICKER_MAP
from db import get_real_inventory, get_past_context, get_recent_journals, has_tag
from constants import (
    TAG_PRAISE_PAST, TAG_DIVIDEND, TAG_SHAKY, TAG_IMPULSE_TRADE,
    TAG_HOLD, TAG_DIDNT_CHECK, TAG_TAKE_BREAK, TAG_MISTAKE
)

MODEL_NAME = "gemini-3.1-flash-lite-preview"

def render_upload_section(supabase, ai_client, selected_tags):
    """이미지 업로드 -> 데이터 검증 -> 최종 분석 섹션 흐름을 관리 및 렌더링합니다."""
    # ---------------------------------------------------------
    # 1단계: 입력 모드
    # ---------------------------------------------------------
    if st.session_state['current_step'] == 'upload_mode':
        st.subheader("📝 오늘의 주식 기록하기")
    
        uploaded_file = st.file_uploader(
            "📸 MTS 캡처 화면 업로드",
            type=["png", "jpg", "jpeg"],
            key=f"uploader_{st.session_state['uploader_key']}"
        )
    
        if uploaded_file is not None:
            original_image = Image.open(uploaded_file).convert("RGB")
    
            st.markdown("### 🛡️ 민감 정보 가림막")
            mask_ratio = st.slider("가림막 높이 조절 (%)", min_value=0, max_value=40, value=20,
                                   help="보통 20% 정도면 계좌 잔고/번호 영역이 가려집니다.")
    
            image = original_image.copy()
            if mask_ratio > 0:
                draw = ImageDraw.Draw(image)
                width, height = image.size
                mask_height = int(height * (mask_ratio / 100.0))
                draw.rectangle(((0, 0), (width, mask_height)), fill="black")
    
            st.image(image, caption='최종 분석용 이미지', use_container_width=True)
    
            if st.button("✅ 가림막 설정 완료 및 정보 추출"):
                with st.spinner('이미지에서 종목과 수량을 읽어오고 있습니다...'):
                    config = types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema={
                            "type": "OBJECT",
                            "additionalProperties": {"type": "NUMBER"},
                        }
                    )
                    extract_prompt = (
                        "이 이미지는 MTS(모바일 트레이딩 앱) 잔고 화면입니다. "
                        "보유 중인 모든 종목명과 수량을 추출해줘. "
                        "숫자에 콤마(,)나 단위는 빼고 순수 숫자만 사용해."
                    )
    
                    text, err = safe_generate(
                        client=ai_client,
                        model_name=MODEL_NAME,
                        contents=[extract_prompt, image],
                        config=config,
                        fallback_msg="이미지 분석 중 오류가 발생했어요."
                    )
    
                    if err:
                        st.error(err)
                        st.info("잠시 후 다시 시도하거나, 아래의 '직접 입력'을 사용해주세요.")
                    else:
                        st.session_state['temp_extracted_data'] = text
                        st.session_state['processed_image'] = image
                        st.session_state['current_step'] = 'verify_data'
                        st.rerun()
    
        st.markdown("---")
        st.write("아이콘이 없는 종목은 직접 입력해주세요.")
    
        with st.form("manual_input_form", clear_on_submit=True):
            col_text, col_btn = st.columns([4, 1])
            with col_text:
                user_text_input = st.text_input("직접 입력", placeholder="예: 삼성전자 10주 매수 완료",
                                                label_visibility="collapsed")
            with col_btn:
                submitted = st.form_submit_button("추가")
    
            if submitted and user_text_input:
                st.session_state['daily_stock_list'].append(f"[직접 입력] {user_text_input}")
                st.success(f"'{user_text_input}' 내용이 추가되었습니다.")
                st.session_state['current_step'] = 'ask_next'
                st.rerun()
    
    # ---------------------------------------------------------
    # 2단계: 추출된 데이터 확인 및 수정 단계 (잔고 비교 → diff → 사유 입력)
    # ---------------------------------------------------------
    if st.session_state.get('current_step') == 'verify_data':
        st.subheader("🔍 변동 내역 확인 및 사유 입력")
    
        if 'processed_image' in st.session_state:
            st.image(st.session_state['processed_image'], caption='비교 확인용 사진', use_container_width=True)
    
        try:
            ai_text = st.session_state.get('temp_extracted_data', '{}')
            extracted_dict = json.loads(ai_text.strip())
            extracted_dict = {k: float(v) for k, v in extracted_dict.items()}
        except Exception as e:
            st.error(f"AI 응답 파싱 실패 ({e}).")
            extracted_dict = {}
    
        current_inventory = {item["종목"]: item["수량"] for item in get_real_inventory(st.session_state["user_id"], supabase)}
    
        diff_data = {}
        for stock, new_qty in extracted_dict.items():
            old_qty = float(current_inventory.get(stock, 0))
            change  = new_qty - old_qty
            if change != 0:
                diff_data[stock] = {"change": change, "old": old_qty, "new": new_qty}
    
        if not diff_data:
            st.success("🎉 DB 잔고와 동일합니다. 새로 변동된 내역이 없습니다.")
        else:
            st.info(f"DB 잔고와 비교해 **{len(diff_data)}개 종목**에 변동이 감지됐습니다. 수량을 확인하고 매매 사유를 적어주세요.")
    
        with st.form(key='verify_diff_form'):
            if diff_data:
                for stock, info in diff_data.items():
                    change = info["change"]
                    badge = "🔴 매도" if change < 0 else "🟢 매수"
                    st.markdown(
                        f"**{stock}** &nbsp; {badge} &nbsp;"
                        f"<span style='color:gray;font-size:0.85em;'>"
                        f"{int(info['old'])}주 → {int(info['new'])}주</span>",
                        unsafe_allow_html=True
                    )
                    col_qty, col_memo = st.columns([1, 2])
                    with col_qty:
                        st.number_input(
                            "변동 수량 (+매수 / -매도)",
                            value=float(change),
                            key=f"qty_{stock}",
                            step=1.0
                        )
                    with col_memo:
                        st.text_input(
                            "매매 사유 (선택)",
                            placeholder="예: 배당금 재투자, 급락 추매",
                            key=f"memo_{stock}"
                        )
                    st.markdown("<hr style='margin:6px 0; border-color:#eee;'>", unsafe_allow_html=True)
    
            col_save, col_cancel = st.columns([7, 3])
            with col_save:
                submit_btn = st.form_submit_button(
                    "💾 확정 및 장바구니 담기",
                    type="primary",
                    disabled=not diff_data
                )
            with col_cancel:
                cancel_btn = st.form_submit_button("취소 및 다시 올리기")
    
            if submit_btn and diff_data:
                for stock in diff_data:
                    final_qty = st.session_state.get(f"qty_{stock}", 0)
                    memo      = st.session_state.get(f"memo_{stock}", "").strip()
                    if final_qty != 0:
                        action   = "매수" if final_qty > 0 else "매도"
                        memo_str = f" (사유: {memo})" if memo else ""
                        st.session_state['daily_stock_list'].append(
                            f"{stock} {abs(final_qty):.0f}주 {action}{memo_str}"
                        )
                st.session_state['current_step'] = 'ask_next'
                st.rerun()
    
            elif cancel_btn:
                st.session_state.pop('temp_extracted_data', None)
                st.session_state.pop('processed_image', None)
                st.session_state['uploader_key'] += 1
                st.session_state['current_step'] = 'upload_mode'
                st.rerun()
    
    # ---------------------------------------------------------
    # 3단계: 추가 입력 여부
    # ---------------------------------------------------------
    if st.session_state.get('current_step') == 'ask_next':
        st.markdown("### 💡 입력을 더 진행하시겠습니까?")
    
        with st.expander("현재까지 입력된 목록 확인", expanded=True):
            for i, item in enumerate(st.session_state['daily_stock_list']):
                col_text, col_del = st.columns([5, 1])
                with col_text:
                    st.write(f"- {item}")
                with col_del:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state['daily_stock_list'].pop(i)
                        st.rerun()
    
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 추가로 입력하기"):
                st.session_state['uploader_key'] += 1
                st.session_state['current_step'] = 'upload_mode'
                st.rerun()
        with col2:
            if st.button("📊 아니오, 이제 분석해주세요"):
                st.session_state['current_step'] = 'final_analysis'
                st.rerun()
    
    # ---------------------------------------------------------
    # 4단계: 최종 분석 및 저장
    # ---------------------------------------------------------
    if st.session_state.get('current_step') == 'final_analysis':
        st.header("📝 오늘의 투자 종합 피드백")
    
        if not st.session_state.get('chosen_mentor'):
            st.warning("⚠️ AI 멘토가 지정되지 않았습니다!")
            st.info("💡 화면 상단의 '🤖 오늘의 멘토 설정' 창을 열어 오늘 대화할 멘토를 선택해주세요.")
            st.session_state['current_step'] = 'upload_mode'
            st.rerun()
    
        chosen_mentor = st.session_state['chosen_mentor']
        all_data_str = "\n".join(st.session_state['daily_stock_list'])
        show_balloons = has_tag(selected_tags, TAG_PRAISE_PAST) or has_tag(selected_tags, TAG_DIVIDEND)
    
        if 'final_result' not in st.session_state and 'final_error' not in st.session_state:
            with st.spinner('오늘의 전체 투자 내역을 바탕으로 멘토가 분석 중입니다...'):
                base_instruction = """당신은 장기 투자자의 매매 일지 작성을 돕는 냉철하고 지혜로운 AI 페이스메이커입니다.
사용자가 매매 메모(텍스트)와 함께 MTS 캡처 사진을 올릴 수 있습니다.

[임무]
1. 사진이 있다면: 데이터(종목, 수량, 수익률)를 정확히 추출하고, 확실치 않으면 사용자에게 되물어보세요.
2. 감정은 무죄, 행동은 유죄: 사용자가 불안감(멘탈흔들림)을 표현하더라도 그 자체를 비난하지 마세요. 충동적인 행동(매도)을 막는 데 집중하세요.
3. 패턴 인지: 제공된 [과거 기록]이 있다면, 이를 분석하여 사용자의 반복되는 실수 패턴이나 감정 패턴을 짚어내고 구체적인 행동(예: 24시간 HTS 삭제, 낮잠 등)을 처방하세요.
"""
    
                system_instruction = base_instruction
    
                # [수정] get_past_context에 st.session_state.get("user_id", "")를 전달하여 보안 강화
                past_records = get_past_context(selected_tags, supabase, st.session_state.get("user_id", ""))
                if past_records:
                    system_instruction += past_records
    
                if has_tag(selected_tags, TAG_PRAISE_PAST) or has_tag(selected_tags, TAG_DIVIDEND):
                    system_instruction += "\n\n[현재 상태: 보상/칭찬] 땀 흘려 번 돈으로 우량 자산을 모아온 사용자의 인내심을 극찬해주세요! 축하와 함께 앞으로도 이 습관을 이어가도록 따뜻하게 격려해주세요."
                elif has_tag(selected_tags, TAG_SHAKY):
                    system_instruction += "\n\n[현재 상태: 불안] 감정은 무죄입니다! 흔들리는 감정을 공감해 주되, 과거 기록을 바탕으로 매도 버튼을 누르지 않도록 멘탈을 꽉 잡아주세요."
                elif has_tag(selected_tags, TAG_IMPULSE_TRADE):
                    system_instruction += "\n\n[현재 상태: 원칙 위반] 사용자가 충동 매매를 했습니다. 뼈 때리는 조언과 함께, 다음 하락장에서는 MTS 앱을 지워버리는 등의 강력한 시스템적 차단 규칙을 제안하세요."
                elif has_tag(selected_tags, TAG_HOLD) or has_tag(selected_tags, TAG_DIDNT_CHECK) or has_tag(selected_tags, TAG_TAKE_BREAK):
                    system_instruction += "\n\n[현재 상태: 능동적 회피 성공] 사용자가 시장을 의도적으로 멀리하거나 충동을 한 템포 늦추는 데 성공했습니다. 이것은 가장 어려운 형태의 자기 통제입니다. 작지만 진심으로 칭찬해주고, 이 패턴을 계속 유지하도록 격려하세요."
    
                if "심리 상담가" in chosen_mentor:
                    system_instruction += "\n\n[말투 지시] 사용자를 심리 상담 센터에 온 내담자처럼 대하세요. 매우 따뜻하고 부드러운 존댓말을 사용하며, 수익률의 등락보다는 사용자의 '감정 상태'와 '마음의 평화'를 어루만지는 데 집중하세요."
                elif "주식 찐친" in chosen_mentor:
                    system_instruction += "\n\n[말투 지시] 10년 지기 동네 친구처럼 100% 편안한 반말로 대답하세요. 장이 좋을 땐 오버하면서 같이 기뻐하고, 하락장일 땐 '야 나도 물렸어 버티자'는 식으로 친근하고 유쾌하게 위로해 주세요."
                elif "1타 강사" in chosen_mentor:
                    system_instruction += "\n\n[말투 지시] 수험생을 가르치는 깐깐한 일타 강사처럼 단호하고 팩트 위주의 말투를 사용하세요. 사용자가 감정에 휘둘릴 때는 매섭게 혼내고, 오직 '원칙 준수'와 '장기 투자'의 중요성만 차갑게 강조하세요."
    
                system_instruction += f"""
\n\n[출력 형식 지시]
사용자의 일기 내용이나 매매 내역을 분석하여 아래의 '정확한 JSON 형식'으로만 답변해 주세요.
절대 다른 마크다운이나 부연 설명을 덧붙이지 마세요.

{{
  "ai_feedback": "...",
  "extracted_trades": [
    {{
      "stock_name": "삼성전자",
      "quantity": 10,
      "type": "buy"
    }}
  ]
}}

[ai_feedback 작성 규칙]
- HTML 태그를 사용하세요. 줄바꿈은 <br><br>, 강조는 <b>텍스트</b>.
- 반드시 아래 3단 구조로 작성하세요:
  1) 따뜻한 공감 인사 (오늘 하루 수고를 알아주는 2~3문장)
  2) 투자 내역에 대한 진심 어린 감상과 격려 (2~3문장, 구체적 종목/행동을 언급)
  3) <b>[오늘의 처방]</b> 로 시작하는 구체적인 행동 처방 1가지 (짧고 실천 가능하게)
- 마치 옆에 앉아 말하듯 사용자를 '투자자님'으로 부르세요.
- 숫자나 종목명을 언급할 때도 차갑게 나열하지 말고 감정과 함께 녹여내세요.

* 주의사항 1: 매수/매도 기록이 없다면 "extracted_trades"는 빈 배열 [] 로 두세요.
* 주의사항 2: 사용자가 주식 종목명, 수량을 입력했거나 이미지에 있다면 반드시 추출하세요. 가격은 추출하지 않아도 됩니다.
* 주의사항 3: extracted_trades의 각 항목에는 stock_name과 quantity만 포함하면 됩니다.
"""
    
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
    
                tag_text = " ".join(selected_tags) if selected_tags else ""
                final_prompt = f"태그: {tag_text}\n\n사용자가 오늘 다음 종목들을 매수/확인했습니다:\n{all_data_str}\n\n이 내역을 바탕으로 전체적인 투자 평과 멘탈 관리 조언을 해줘."
    
                final_text, err = safe_generate(
                    client=ai_client,
                    model_name=MODEL_NAME,
                    contents=final_prompt,
                    config=config,
                    fallback_msg="최종 피드백 생성 중 오류가 발생했어요."
                )
    
                if err:
                    st.session_state['final_error'] = err
                else:
                    try:
                        ai_data = json.loads(final_text.strip())
                        ai_feedback = ai_data.get("ai_feedback", "기록이 저장되었습니다.")
                        extracted_trades = ai_data.get("extracted_trades", [])
    
                        st.session_state['final_result'] = ai_feedback
    
                        # DB 저장 준비
                        trades_to_insert = []
                        if extracted_trades:
                            tickers_to_fetch = []
                            for trade in extracted_trades:
                                raw_name   = trade["stock_name"]
                                normalized = " ".join(raw_name.split())
                                ticker     = TICKER_MAP.get(normalized) or TICKER_MAP.get(raw_name)
                                trade["_normalized_name"] = normalized
                                trade["_ticker"]          = ticker
                                if ticker:
                                    tickers_to_fetch.append(ticker)
    
                            bulk_trade_prices = get_realtime_prices_bulk(tuple(tickers_to_fetch), time_bucket=_market_time_bucket()) if tickers_to_fetch else {}
    
                            for trade in extracted_trades:
                                ticker = trade["_ticker"]
                                if ticker:
                                    real_price = bulk_trade_prices.get(ticker) or 0.0
                                    currency   = "KRW" if ticker.endswith(".KS") else "USD"
                                else:
                                    real_price = 0.0
                                    currency   = "KRW"
                                
                                trades_to_insert.append({
                                    "stock_name": trade["_normalized_name"],
                                    "quantity":   abs(trade["quantity"]),
                                    "price":      real_price,
                                    "currency":   currency,
                                    "type":       trade.get("type", "buy")
                                })
    
                        # DB 실제 저장
                        tags_str = ", ".join(selected_tags) if selected_tags else ""
                        _uid = st.session_state["user_id"]
                        supabase.table("journals").insert({
                            "user_id":     _uid,
                            "tags":        tags_str,
                            "content":     all_data_str,
                            "ai_feedback": ai_feedback,
                        }).execute()
                        get_recent_journals.clear()
    
                        if trades_to_insert:
                            for t in trades_to_insert:
                                t["user_id"] = _uid
                            supabase.table("trades").insert(trades_to_insert).execute()
                        get_real_inventory.clear()
                                
                    except json.JSONDecodeError as e:
                        st.session_state['final_error'] = f"JSON 파싱 실패: {e}\n\n원본 응답:\n{final_text}"
                    except Exception as e:
                        st.error(f"⚠️ 저장 중 오류: {e}")
                        st.session_state['final_error'] = f"저장 실패: {e}"
    
        if 'final_error' in st.session_state:
            st.error(st.session_state['final_error'])
            st.info("위 오류가 일시적인 것 같으면 잠시 후 다시 시도해주세요. **입력하신 내역은 아직 저장되지 않았습니다.**")
        elif 'final_result' in st.session_state:
            if show_balloons and not st.session_state.get('balloons_shown'):
                st.balloons()
                st.session_state['balloons_shown'] = True
            if not st.session_state.get('toast_shown'):
                st.toast("일기와 매매 기록이 창고에 입고되었습니다!", icon="📦")
                st.session_state['toast_shown'] = True
            st.markdown(st.session_state['final_result'], unsafe_allow_html=True)
    
        if st.button("🔄 처음으로 돌아가기"):
            st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
            for key in ['daily_stock_list', 'current_step', 'temp_extracted_data', 'balloons_shown',
                        'toast_shown', 'processed_image', 'current_tags', 'chat_messages',
                        'final_result', 'final_error']:
                st.session_state.pop(key, None)
            st.rerun()
