import streamlit as st
import json
import datetime
import pandas as pd
import textwrap
from db import to_kst_str, get_recent_journals, get_real_inventory
from prices import resolve_ticker
from ai_helper import ai_resolve_ticker
from app_constants import KST
from ui_components import card, banner
from auth import validate_password

def render_settings_tab(supabase, ai_client=None, model_name=None, dev_mode=False):
    st.markdown("### ⚙️ 설정 및 데이터 관리")
    st.markdown("<p style='color: #4E5968; font-size: 0.95em;'>비밀번호를 재설정하거나 안전하게 데이터를 백업 및 삭제할 수 있습니다.</p>", unsafe_allow_html=True)

    # ── 📖 앱 사용 설명서 (최상단 배치) ──────────────────────────────────
    with st.expander("📖 AI 주식 다이어리 핵심 사용 가이드", expanded=True):
        guide_html = """
        <div style="font-family: Pretendard, sans-serif; line-height: 1.6; color: #333D4B;">
            <p style="font-size: 0.92em; color: #4E5968; margin-bottom: 20px;">
                이 다이어리는 투자 기록 관리(Track 1)와 AI 심리 코칭(Track 2)을 결합하여 
                장기 투자를 끈기 있게 완수할 수 있도록 돕는 스마트 개인 포트폴리오 솔루션입니다.
            </p>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 20px;">
                
                <!-- Track 1 카드 -->
                <div style="background: #F8F9FA; border-radius: 14px; padding: 18px; border: 1px solid #F2F4F6;">
                    <div style="font-weight: 700; font-size: 1.02em; color: #3182F6; margin-bottom: 10px; display: flex; align-items: center;">
                        <span style="font-size: 1.25em; margin-right: 8px;">📸</span> Track 1: 투자 자산 기록
                    </div>
                    <ul style="margin: 0; padding-left: 18px; font-size: 0.88em; color: #4E5968; line-height: 1.6;">
                        <li><b>스크린샷 인식:</b> 매수 잔고 화면(KB증권, 영웅문 등) 캡처 이미지를 일기장 탭에 올리세요.</li>
                        <li><b>자동 검증 절차:</b> AI가 인식한 수량·평단가를 보여주며, 기존 보유 주식과의 일치 여부를 정밀 검증 후 저장합니다.</li>
                        <li><b>수동 기입 지원:</b> 수동 입력 모드를 통해 일괄/개별 거래 내역도 직접 기입할 수 있습니다.</li>
                    </ul>
                </div>
                
                <!-- Track 2 카드 -->
                <div style="background: #F8F9FA; border-radius: 14px; padding: 18px; border: 1px solid #F2F4F6;">
                    <div style="font-weight: 700; font-size: 1.02em; color: #10B981; margin-bottom: 10px; display: flex; align-items: center;">
                        <span style="font-size: 1.25em; margin-right: 8px;">💬</span> Track 2: 멘탈 조절 & 피드백
                    </div>
                    <ul style="margin: 0; padding-left: 18px; font-size: 0.88em; color: #4E5968; line-height: 1.6;">
                        <li><b>심리 태그:</b> 불안하다, 매도 충동, 홀가분하다 등 현재 감정 상태의 태그를 클릭해 활성화해 보세요.</li>
                        <li><b>맞춤 멘토 코칭:</b> 사이드바에서 멘토 유형(츤데레, 냉철, 따뜻 등)을 고르면 그에 맞는 맞춤 답변을 실시간으로 제공합니다.</li>
                        <li><b>하단 탭바 & 채팅:</b> 모바일 화면에 맞춰 탭바가 하단에 고정되며, 엔터 키 전송을 지원하는 네이티브 채팅창으로 대화합니다.</li>
                    </ul>
                </div>
                
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 12px;">
                
                <!-- 보물함 카드 -->
                <div style="background: #F8F9FA; border-radius: 14px; padding: 18px; border: 1px solid #F2F4F6;">
                    <div style="font-weight: 700; font-size: 1.02em; color: #EAB308; margin-bottom: 10px; display: flex; align-items: center;">
                        <span style="font-size: 1.25em; margin-right: 8px;">👑</span> 보물함 (실시간 시세 연동)
                    </div>
                    <ul style="margin: 0; padding-left: 18px; font-size: 0.88em; color: #4E5968; line-height: 1.6;">
                        <li><b>실시간 평가:</b> Yahoo Finance API와 실시간 연동되어 내 보유 자산의 가치와 수익률을 계산합니다.</li>
                        <li><b>경제적 자유 게이지:</b> 목표 배당금 수령에 맞춰 그라데이션 프로그레스 바가 차오릅니다.</li>
                        <li><b>가족 분담금 역할극:</b> 배당 기여도에 따라 '든든한 맏형', '야무진 막내' 등 배당금이 의인화되어 재미를 줍니다.</li>
                    </ul>
                </div>

                <!-- 꿀팁 카드 -->
                <div style="background: #EBF5FF; border-radius: 14px; padding: 18px; border: 1px solid #D0E6FF;">
                    <div style="font-weight: 700; font-size: 1.02em; color: #1B64DA; margin-bottom: 10px; display: flex; align-items: center;">
                        <span style="font-size: 1.25em; margin-right: 8px;">💡</span> 실전 다이어리 200% 활용 팁
                    </div>
                    <ul style="margin: 0; padding-left: 18px; font-size: 0.88em; color: #1B64DA; line-height: 1.6;">
                        <li>매매가 없는 날이라도 가벼운 멘탈 일기나 감정 태그만 기록해 두면 AI가 미래의 흔들리는 내 멘탈을 위한 <b>과거 데이터 처방전</b>을 쓸 수 있습니다.</li>
                        <li>실시간 가격 연동을 위해서는 각 종목별 <b>야후파이낸스 티커(Ticker)</b> 매치 상태를 점검해 보세요.</li>
                    </ul>
                </div>
                
            </div>
        </div>
        """
        st.markdown(textwrap.dedent(guide_html), unsafe_allow_html=True)

    # 1. 비밀번호 변경
    st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🔑 비밀번호 변경")
    
    with st.form("change_pw_form", clear_on_submit=True):
        cp_new = st.text_input("새 비밀번호", type="password", placeholder="8자리 이상 (영문+숫자 포함)")
        cp_new2 = st.text_input("새 비밀번호 확인", type="password", placeholder="한번 더 입력해주세요")
        cp_btn = st.form_submit_button("변경 사항 저장", type="primary")
        
    if cp_btn:
        if not cp_new or not cp_new2:
            banner("비밀번호 항목을 모두 입력해주세요.", type="warning")
        elif cp_new != cp_new2:
            banner("입력하신 두 비밀번호가 일치하지 않습니다.", type="error")
        elif validate_password(cp_new):
            banner(validate_password(cp_new), type="warning")
        else:
            try:
                supabase.auth.update_user({"password": cp_new})
                banner("비밀번호가 성공적으로 변경되었습니다. 🎉", type="success")
            except Exception as e:
                banner(f"변경에 실패했습니다: {e}", type="error")

    # 2. 내 일기 데이터 내보내기
    st.markdown("---")
    st.markdown("#### 💾 데이터 내보내기 및 백업")
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em; margin-bottom: 12px;'>사용자가 기록한 모든 주식 일기와 AI 피드백을 JSON 파일로 즉시 다운로드하여 소장할 수 있습니다.</p>", unsafe_allow_html=True)

    _uid = st.session_state.get("user_id")
    today_str = datetime.datetime.now(KST).strftime("%Y%m%d")

    try:
        all_rows = (
            supabase.table("journals")
            .select("created_at, tags, content, ai_feedback")
            .eq("user_id", _uid)
            .order("created_at", desc=True)
            .execute()
            .data
        )

        if all_rows:
            export_data = [{
                "created_at_kst": to_kst_str(r["created_at"]),
                "tags": r.get("tags") or "",
                "content": r.get("content") or "",
                "ai_feedback": r.get("ai_feedback") or "",
            } for r in all_rows]

            json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")

            st.download_button(
                label=f"📥 내 일기 {len(all_rows)}개 백업 파일 다운로드 (.json)",
                data=json_bytes,
                file_name=f"my_stock_diary_backup_{today_str}.json",
                mime="application/json",
            )
        else:
            banner("아직 저장된 일기가 없어서 백업을 생성할 수 없습니다.", type="info")
    except Exception as e:
        banner(f"백업 데이터 조회 실패: {e}", type="error")

    # 3. 티커 관리자
    st.markdown("---")
    st.markdown("#### 🎯 티커 관리자")
    st.markdown(
        "<p style='color: #4E5968; font-size: 0.92em;'>"
        "자동으로 연결되지 않은 종목이나 잘못 연결된 종목의 야후파이낸스 티커를 직접 수정할 수 있습니다. "
        "수정한 티커는 보물함 실시간 가격에 즉시 반영됩니다."
        "</p>",
        unsafe_allow_html=True,
    )

    with st.expander("📖 티커 찾는 방법 — 미장 / 국장 / 한국 ETF 완전 매뉴얼", expanded=False):
        ticker_manual_html = """
        <div style="font-family: Pretendard, sans-serif; line-height: 1.6; color: #333D4B;">
            <h4 style="font-size: 1.15em; font-weight: 700; color: #191F28; margin-top: 0; margin-bottom: 8px;">💡 야후파이낸스 티커(Ticker)란?</h4>
            <p style="font-size: 0.9em; color: #4E5968; margin-bottom: 20px;">
                본 앱은 글로벌 금융 시세망인 <b>Yahoo Finance API</b>를 통해 실시간/종가 시세를 가져옵니다. 
                정확한 가격 표시를 위해 각 자산 유형별 코드(티커) 규칙을 참고하여 등록해 주세요.
            </p>
            
            <!-- 1. 국가/자산별 입력 가이드 -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 24px;">
                
                <!-- 미장 가이드 -->
                <div style="background: #F8F9FA; border-radius: 12px; padding: 18px; border: 1px solid #F2F4F6;">
                    <div style="font-weight: 700; font-size: 1em; color: #191F28; margin-bottom: 12px; display: flex; align-items: center;">
                        <span style="font-size: 1.2em; margin-right: 8px;">🇺🇸</span> 미국 주식 / ETF
                    </div>
                    <div style="font-size: 0.88em; color: #4E5968;">
                        <b style="color: #3182F6;">규칙:</b> 영문 심볼 그대로 입력 (대문자)<br>
                        <div style="background: #FFFFFF; padding: 10px; border-radius: 8px; border: 1px solid #E5E8EB; margin: 8px 0; font-family: monospace; font-size: 0.9em;">
                            애플 &rarr; <b>AAPL</b><br>
                            테슬라 &rarr; <b>TSLA</b><br>
                            S&P 500 ETF &rarr; <b>VOO</b><br>
                            배당 다우존스 &rarr; <b>SCHD</b>
                        </div>
                        <b>🔍 시세 검색 사이트:</b><br>
                        <a href="https://finance.yahoo.com" target="_blank" style="color: #3182F6; text-decoration: none; font-weight: 600;">Yahoo Finance ↗</a> 에서 종목 검색 후 URL의 <code>/quote/<b>XXXX</b></code> 부분이 티커입니다.
                    </div>
                </div>
                
                <!-- 국장 가이드 -->
                <div style="background: #F8F9FA; border-radius: 12px; padding: 18px; border: 1px solid #F2F4F6;">
                    <div style="font-weight: 700; font-size: 1em; color: #191F28; margin-bottom: 12px; display: flex; align-items: center;">
                        <span style="font-size: 1.2em; margin-right: 8px;">🇰🇷</span> 한국 주식 (코스피/코스닥)
                    </div>
                    <div style="font-size: 0.88em; color: #4E5968;">
                        <b style="color: #3182F6;">규칙:</b> 종목코드 6자리 + 시장구분코드<br>
                        <span style="font-size: 0.85em; opacity: 0.85;">(코스피: <code>.KS</code> / 코스닥: <code>.KQ</code>)</span>
                        <div style="background: #FFFFFF; padding: 10px; border-radius: 8px; border: 1px solid #E5E8EB; margin: 8px 0; font-family: monospace; font-size: 0.9em;">
                            삼성전자 (코스피) &rarr; <b>005930.KS</b><br>
                            SK하이닉스 (코스피) &rarr; <b>000660.KS</b><br>
                            알테오젠 (코스닥) &rarr; <b>196170.KQ</b>
                        </div>
                        <b>🔍 코드 검색 사이트:</b><br>
                        <a href="https://finance.naver.com" target="_blank" style="color: #3182F6; text-decoration: none; font-weight: 600;">네이버페이 증권 ↗</a> 에서 종목을 검색했을 때 나오는 숫자 6자리 코드입니다.
                    </div>
                </div>
                
                <!-- 한국 ETF 가이드 -->
                <div style="background: #F8F9FA; border-radius: 12px; padding: 18px; border: 1px solid #F2F4F6;">
                    <div style="font-weight: 700; font-size: 1em; color: #191F28; margin-bottom: 12px; display: flex; align-items: center;">
                        <span style="font-size: 1.2em; margin-right: 8px;">🏦</span> 한국 ETF (KODEX, TIGER 등)
                    </div>
                    <div style="font-size: 0.88em; color: #4E5968;">
                        <b style="color: #3182F6;">규칙:</b> ETF코드 6자리 + <code>.KS</code><br>
                        <span style="font-size: 0.85em; opacity: 0.85;">(한국 ETF는 99% 코스피 시장 상장)</span>
                        <div style="background: #FFFFFF; padding: 10px; border-radius: 8px; border: 1px solid #E5E8EB; margin: 8px 0; font-family: monospace; font-size: 0.9em;">
                            KODEX 200 &rarr; <b>069500.KS</b><br>
                            TIGER 미국S&P500 &rarr; <b>360750.KS</b><br>
                            ACE 미국배당다우존스 &rarr; <b>402970.KS</b>
                        </div>
                        <b>🔍 시세 검색 사이트:</b><br>
                        <a href="https://finance.naver.com/fund/etfItemList.naver" target="_blank" style="color: #3182F6; text-decoration: none; font-weight: 600;">네이버 ETF 목록 바로가기 ↗</a>
                    </div>
                </div>
                
            </div>
            
            <!-- 2. 대량 등록 및 실전 활용 흐름 -->
            <div style="background: #EBF5FF; border-radius: 12px; padding: 18px; border: 1px solid #D0E6FF; margin-bottom: 20px;">
                <div style="font-weight: 700; font-size: 0.95em; color: #1B64DA; margin-bottom: 10px; display: flex; align-items: center;">
                    <span style="font-size: 1.2em; margin-right: 8px;">🛠️</span> 꿀팁: 엑셀 VLOOKUP으로 한 번에 티커 채우기
                </div>
                <ol style="margin: 0; padding-left: 20px; font-size: 0.85em; color: #2B579A; line-height: 1.6;">
                    <li>한국거래소(<a href="https://data.krx.co.kr" target="_blank" style="color:#1B64DA; font-weight:600;">KRX 정보데이터시스템 ↗</a>) 등에서 전체 ETF 종목코드(6자리) 다운로드</li>
                    <li>엑셀 수식으로 티커 열을 완성합니다: <code>=종목코드&".KS"</code></li>
                    <li>설정 메뉴의 <b>CSV 다운로드</b> 버튼으로 내 보유종목 템플릿을 내려받습니다.</li>
                    <li>엑셀 <code>VLOOKUP</code> 함수를 사용하여 내 종목명에 맞는 티커를 한 번에 자동 매칭합니다.</li>
                    <li>완성된 CSV 파일을 하단의 <b>'티커 파일 업로드'</b>에 올리면 <b>1초 만에 완료!</b></li>
                </ol>
            </div>
            
            <!-- 3. 주의사항 -->
            <div style="background: #FFF9DB; border-radius: 12px; padding: 16px; border: 1px solid #FFE066; font-size: 0.85em; color: #665200; line-height: 1.5; margin-bottom: 8px;">
                <b>⚠️ 등록 시 유의사항:</b><br>
                • 티커가 정확하지 않으면 엉뚱한 가격이 표시되거나 가격 불러오기가 지연(📡)될 수 있습니다.<br>
                • 잘못 설정했을 때 해당 칸을 빈칸으로 두고 저장하면 기본 규칙(자동 연결)으로 자동 리셋됩니다.<br>
                • 실시간 가격이 연동되지 않을 땐 Yahoo Finance에 입력한 코드를 직접 검색해 보세요.
            </div>
        </div>
        """
        st.markdown(textwrap.dedent(ticker_manual_html), unsafe_allow_html=True)

    # ── 티커 편집 테이블 ──────────────────────────────────
    _uid = st.session_state.get("user_id", "")
    inventory = get_real_inventory(_uid, supabase) if _uid else []

    # 자동 매칭 결과 표시 (rerun 후 세션에서 꺼내서 보여줌)
    if "_ticker_auto_result" in st.session_state:
        result = st.session_state.pop("_ticker_auto_result")
        if result.get("matched"):
            banner(
                f"✅ {len(result['matched'])}개 종목 자동 연결 완료!\n\n" + "\n\n".join(result["matched"]),
                type="success",
            )
        if result.get("unmatched"):
            banner(
                f"⚠️ {len(result['unmatched'])}개 종목은 자동 매칭 실패 — 아래 표에서 직접 입력해 주세요:\n\n"
                + ", ".join(result["unmatched"]),
                type="warning",
            )

    if not inventory:
        banner("현재 보물함에 보유 종목이 없습니다. 매수 기록을 먼저 추가해 주세요.", type="info")
    else:
        # 현재 티커 상태 계산
        rows = []
        for item in inventory:
            stored = item.get("ticker") or ""
            auto   = resolve_ticker(item["종목"]) or ""
            current = stored or auto
            if current:
                status = "✅ 자동 연결" if not stored and auto else ("✅ 수동 설정" if stored else "✅ 자동 연결")
            else:
                status = "⚠️ 미연결"
            rows.append({
                "종목명":          item["종목"],
                "티커":            current,
                "상태":            status,
                "보유 수량":       item["수량"],
            })

        # ── 액션 버튼 영역 ───────────────────────────────────
        col_auto, col_dl, col_info = st.columns([2, 2, 3])
        with col_auto:
            auto_btn = st.button(
                "야후파이낸스 기준 자동 매칭",
                type="primary",
                width='stretch',
                help="미연결 종목의 티커를 KRX 데이터베이스와 야후파이낸스 규칙으로 자동으로 찾아 저장합니다.",
            )
        with col_dl:
            if dev_mode:
                import io as _io
                _csv_rows = []
                for _r in rows:
                    _csv_rows.append({"종목명": _r["종목명"], "야후파이낸스_티커": _r["티커"]})
                _csv_df = pd.DataFrame(_csv_rows)
                _csv_buf = _io.StringIO()
                _csv_df.to_csv(_csv_buf, index=False, encoding="utf-8-sig")
                st.download_button(
                    label="CSV 다운로드",
                    data=_csv_buf.getvalue().encode("utf-8-sig"),
                    file_name="ticker_list.csv",
                    mime="text/csv",
                    width='stretch',
                    help="종목명·티커 목록을 CSV로 받아 엑셀에서 편집한 뒤 아래 업로드 버튼으로 올리세요.",
                )
        with col_info:
            if dev_mode:
                st.caption("⚡ 자동 매칭은 미연결(⚠️) 종목만 · CSV로 일괄 수정도 가능합니다.")
            else:
                st.caption("⚡ 자동 매칭은 미연결(⚠️) 종목만 대상입니다.")

        # ── CSV 업로드 (일괄 티커 등록 — 관리자 전용) ───────
        if dev_mode:
            st.markdown(
                "<p style='color:#4E5968; font-size:0.88em; margin:4px 0 8px 0;'>"
                "CSV 다운로드 → 엑셀에서 티커 입력 → 아래에 업로드하면 한 번에 저장됩니다."
                "</p>",
                unsafe_allow_html=True,
            )
            uploaded_csv = st.file_uploader(
                "티커가 입력된 CSV 파일 업로드",
                type=["csv"],
                key="ticker_csv_uploader",
                help="CSV 다운로드 후 '야후파이낸스_티커' 열을 채워서 다시 올려주세요.",
            )
            if uploaded_csv is not None:
                try:
                    import io as _io2
                    _up_df = pd.read_csv(_io2.BytesIO(uploaded_csv.read()))
                    _up_df.columns = [c.strip() for c in _up_df.columns]
                    if "종목명" not in _up_df.columns or "야후파이낸스_티커" not in _up_df.columns:
                        banner("CSV 형식 오류: '종목명'과 '야후파이낸스_티커' 컬럼이 필요합니다.", type="error")
                    else:
                        st.dataframe(_up_df, use_container_width=True, hide_index=True)
                        if st.button("이 내용으로 티커 일괄 저장", type="primary", key="csv_upload_save_btn"):
                            saved, skipped, errors = 0, 0, []
                            for _, _row in _up_df.iterrows():
                                _name = str(_row.get("종목명", "")).strip()
                                _ticker = str(_row.get("야후파이낸스_티커", "")).strip().upper()
                                if not _name or _ticker in ("", "NAN", "NONE"):
                                    skipped += 1
                                    continue
                                try:
                                    supabase.table("trades") \
                                        .update({"ticker": _ticker}) \
                                        .eq("user_id", _uid) \
                                        .eq("stock_name", _name) \
                                        .execute()
                                    saved += 1
                                except Exception as _e:
                                    errors.append(f"{_name}: {_e}")
                            get_real_inventory.clear()
                            if errors:
                                banner(f"일부 저장 실패:\n" + "\n".join(errors), type="error")
                            else:
                                msg = f"✅ {saved}개 종목 티커 저장 완료!"
                                if skipped:
                                    msg += f" ({skipped}개 빈 티커는 건너뜀)"
                                banner(msg, type="success")
                            st.rerun()
                except Exception as _e:
                    banner(f"CSV 파일 읽기 실패: {_e}", type="error")

        if auto_btn:
            targets = [item for item in inventory if not item.get("ticker")]
            if not targets:
                banner("모든 종목이 이미 티커와 연결되어 있습니다!", type="success")
            else:
                matched, unmatched = [], []
                with st.spinner(f"{len(targets)}개 종목 티커 자동 조회 중... (KRX 조회 포함, 최초 1회는 오래 걸릴 수 있어요)"):
                    for item in targets:
                        found = resolve_ticker(item["종목"])
                        if not found and ai_client and model_name:
                            found = ai_resolve_ticker(ai_client, model_name, item["종목"])
                        if found:
                            try:
                                supabase.table("trades") \
                                    .update({"ticker": found}) \
                                    .eq("user_id", _uid) \
                                    .eq("stock_name", item["종목"]) \
                                    .execute()
                                matched.append(f"{item['종목']} → **{found}**")
                            except Exception:
                                unmatched.append(item["종목"])
                        else:
                            unmatched.append(item["종목"])

                get_real_inventory.clear()
                st.session_state["_ticker_auto_result"] = {
                    "matched": matched,
                    "unmatched": unmatched,
                }
                st.rerun()

        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

        df_orig = pd.DataFrame(rows)
        df_edit = st.data_editor(
            df_orig,
            column_config={
                "종목명":    st.column_config.TextColumn("종목명",         disabled=True, width="medium"),
                "티커":      st.column_config.TextColumn("야후파이낸스 티커", help="예: 005930.KS / SCHD / AAPL", width="medium"),
                "상태":      st.column_config.TextColumn("현재 상태",       disabled=True, width="small"),
                "보유 수량": st.column_config.NumberColumn("보유 수량",     disabled=True, width="small"),
            },
            width='stretch',
            hide_index=True,
            key="ticker_editor",
        )

        if st.button("티커 변경사항 저장", type="primary"):
            changed = 0
            errors  = []
            for _, row in df_edit.iterrows():
                orig_row = df_orig[df_orig["종목명"] == row["종목명"]].iloc[0]
                new_ticker = (row["티커"] or "").strip().upper()
                old_ticker = (orig_row["티커"] or "").strip().upper()
                if new_ticker == old_ticker:
                    continue  # 변경 없으면 스킵
                try:
                    supabase.table("trades") \
                        .update({"ticker": new_ticker or None}) \
                        .eq("user_id", _uid) \
                        .eq("stock_name", row["종목명"]) \
                        .execute()
                    changed += 1
                except Exception as e:
                    errors.append(f"{row['종목명']}: {e}")

            if errors:
                banner(f"일부 저장 실패:\n" + "\n".join(errors), type="error")
            elif changed == 0:
                banner("변경된 티커가 없습니다.", type="info")
            else:
                get_real_inventory.clear()
                banner(f"✅ {changed}개 종목의 티커가 업데이트됐습니다! 보물함에서 확인해 보세요.", type="success")
                st.rerun()

    # 4. 데이터 보안 및 개인정보 처리방침
    st.markdown("---")
    st.markdown("#### 🛡️ 데이터 보안 및 개인정보 처리방침")
    st.markdown(
        "🔒 **안전한 데이터 보관 환경**\n\n"
        "이 서비스의 모든 개인 데이터는 철저하게 암호화되어 글로벌 보안 표준을 준수하는 "
        "**Supabase Cloud** 데이터베이스에 안전하게 보관됩니다.\n\n"
        "- **독립된 유저 공간:** 개별 사용자 정보는 행 단위 보안 정책(RLS, Row Level Security)에 의해 "
        "타인이 절대 조회할 수 없도록 철저히 격리됩니다.\n"
        "- **휘발성 AI 분석:** AI 멘토와의 일시적인 대화나 분석 목적의 캡처 이미지는 저장되지 않고 "
        "세션 종료 즉시 메모리에서 영구 삭제됩니다."
    )


    # 6. 앱 로그 뷰어 (dev_mode 전용)
    if dev_mode:
        st.markdown("---")
        st.markdown("#### 📊 앱 이벤트 로그 (관리자 전용)")
        st.caption("app_logs 테이블의 최근 이벤트를 조회합니다.")

        log_level_filter = st.selectbox(
            "레벨 필터",
            ["전체", "INFO", "WARNING", "ERROR"],
            key="log_level_filter",
        )
        log_limit = st.slider("조회 건수", min_value=10, max_value=200, value=50, step=10, key="log_limit")

        if st.button("🔄 로그 새로고침", key="refresh_logs_btn"):
            st.rerun()

        try:
            q = supabase.table("app_logs").select("created_at, level, event, message, user_id, extra")
            if log_level_filter != "전체":
                q = q.eq("level", log_level_filter)
            logs = q.order("created_at", desc=True).limit(log_limit).execute().data

            if logs:
                log_rows = []
                for r in logs:
                    log_rows.append({
                        "시각": r.get("created_at", "")[:19].replace("T", " "),
                        "레벨": r.get("level", ""),
                        "이벤트": r.get("event", ""),
                        "메시지": r.get("message", ""),
                        "user_id": (r.get("user_id") or "")[:8],
                        "extra": str(r.get("extra") or ""),
                    })
                st.dataframe(
                    pd.DataFrame(log_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "시각":    st.column_config.TextColumn(width="medium"),
                        "레벨":    st.column_config.TextColumn(width="small"),
                        "이벤트":  st.column_config.TextColumn(width="small"),
                        "메시지":  st.column_config.TextColumn(width="large"),
                        "user_id": st.column_config.TextColumn(width="small"),
                        "extra":   st.column_config.TextColumn(width="large"),
                    },
                )

                # Excel 한글 깨짐 방지를 위해 utf-8-sig 인코딩 적용하여 다운로드 추가
                df_download = pd.DataFrame(logs)
                df_download["created_at_kst"] = df_download["created_at"].apply(to_kst_str)
                df_download = df_download[["created_at_kst", "level", "event", "message", "user_id", "extra"]]
                df_download.columns = ["발생시각(KST)", "로그레벨", "이벤트", "메시지", "사용자ID", "상세데이터"]
                csv_data = df_download.to_csv(index=False, encoding="utf-8-sig")

                st.download_button(
                    label=f"📥 조회된 로그 {len(logs)}개 CSV 다운로드",
                    data=csv_data,
                    file_name=f"admin_app_logs_{today_str}.csv",
                    mime="text/csv",
                    key="admin_log_download_btn",
                )
            else:
                banner("조건에 맞는 로그가 없습니다.", type="info")
        except Exception as e:
            banner(f"로그 조회 실패: {e}", type="error")

    # 7. 계정 데이터 영구 삭제
    st.markdown("---")
    st.markdown("<h4 style='color: #E03131;'>⚠️ 계정 데이터 삭제</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em;'>이 작업은 복구가 불가능합니다. 신중히 결정해 주세요.</p>", unsafe_allow_html=True)

    with st.expander("🚨 나의 기록 데이터 영구 삭제"):
        st.caption("⚠️ 주의: 일기 및 매매 기록만 삭제됩니다. 계정(이메일/비밀번호)은 유지되므로 같은 계정으로 다시 로그인할 수 있습니다.")
        confirm = st.text_input('본인 확인을 위해 아래 입력창에 "삭제합니다"를 입력해주세요', key="delete_confirm")
        if st.button("내 기록 데이터 영구 삭제", type="primary"):
            if confirm == "삭제합니다":
                try:
                    _uid = st.session_state["user_id"]
                    supabase.table("journals").delete().eq("user_id", _uid).execute()
                    supabase.table("trades").delete().eq("user_id", _uid).execute()
                    get_recent_journals.clear()
                    get_real_inventory.clear()
                    # 세션도 완전히 비워서 로그아웃 상태로 전환
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
                except Exception as e:
                    banner(f"삭제에 실패했습니다: {e}", type="error")
            else:
                banner("확인 문구가 정확하지 않습니다. 다시 입력해주세요.", type="warning")
