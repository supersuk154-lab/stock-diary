import streamlit as st
import json
import datetime
import pandas as pd
from db import to_kst_str, get_recent_journals, get_real_inventory
from prices import resolve_ticker
from app_constants import KST
from ui_components import card, banner
from auth import validate_password

def render_settings_tab(supabase):
    st.markdown("### ⚙️ 설정 및 데이터 관리")
    st.markdown("<p style='color: #4E5968; font-size: 0.95em;'>비밀번호를 재설정하거나 안전하게 데이터를 백업 및 삭제할 수 있습니다.</p>", unsafe_allow_html=True)

    # 1. 비밀번호 변경
    st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🔑 비밀번호 변경")
    
    with st.form("change_pw_form", clear_on_submit=True):
        cp_new = st.text_input("새 비밀번호", type="password", placeholder="8자리 이상 (영문+숫자 포함)")
        cp_new2 = st.text_input("새 비밀번호 확인", type="password", placeholder="한번 더 입력해주세요")
        cp_btn = st.form_submit_button("🔒 변경 사항 저장", type="primary")
        
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

    try:
        _uid = st.session_state.get("user_id")
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
            today_str = datetime.datetime.now(KST).strftime("%Y%m%d")

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

    with st.expander("📖 티커 찾는 방법 (처음이라면 꼭 읽어보세요)", expanded=False):
        st.markdown(
            "### 야후파이낸스 티커란?\n"
            "야후파이낸스는 전 세계 주식의 실시간 가격을 제공하는 사이트입니다. "
            "이 앱은 야후파이낸스 API로 가격을 가져오기 때문에, **야후파이낸스 기준의 티커 코드**가 필요합니다.\n\n"
        )
        st.info(
            "**🔍 티커 찾는 방법 (공통)**\n\n"
            "1. [finance.yahoo.com](https://finance.yahoo.com) 접속\n"
            "2. 검색창에 종목명 입력 (예: 삼성전자, SCHD)\n"
            "3. 검색 결과에서 내 종목 클릭\n"
            "4. URL 또는 종목명 옆에 표시된 **굵은 영문+숫자 코드**가 티커입니다\n\n"
            "예) 삼성전자 검색 → URL이 `/quote/005930.KS` → 티커는 **005930.KS**"
        )
        col_kr, col_us = st.columns(2)
        with col_kr:
            st.success(
                "**🇰🇷 한국 주식 형식**\n\n"
                "```\n"
                "KOSPI 종목: 숫자6자리.KS\n"
                "  삼성전자   → 005930.KS\n"
                "  카카오     → 035720.KS\n"
                "  SK하이닉스 → 000660.KS\n\n"
                "KOSDAQ 종목: 숫자6자리.KQ\n"
                "  에코프로   → 086520.KQ\n"
                "  셀트리온   → 068270.KQ\n"
                "```\n\n"
                "💡 종목코드 6자리는 **네이버페이 증권** 또는 "
                "**한국거래소(krx.co.kr)** 에서도 확인 가능합니다."
            )
        with col_us:
            st.info(
                "**🇺🇸 미국 주식/ETF 형식**\n\n"
                "```\n"
                "그냥 심볼 그대로 입력:\n"
                "  애플       → AAPL\n"
                "  엔비디아   → NVDA\n"
                "  S&P500 ETF → VOO\n"
                "  배당 ETF   → SCHD\n"
                "  나스닥 ETF → QQQ\n"
                "  버크셔B    → BRK-B\n"
                "```\n\n"
                "💡 영문 심볼 1~5자리는 대부분 **자동 연결**됩니다. "
                "연결이 안 된 경우만 직접 입력하세요."
            )
        st.warning(
            "⚠️ **주의사항**\n\n"
            "- 티커를 잘못 입력하면 엉뚱한 종목 가격이 표시될 수 있습니다.\n"
            "- 저장 전 야후파이낸스에서 해당 티커로 검색해 맞는지 꼭 확인하세요.\n"
            "- 입력 후 보물함에서 가격이 뜨지 않으면 티커가 틀린 겁니다."
        )

    # ── 티커 편집 테이블 ──────────────────────────────────
    _uid = st.session_state.get("user_id", "")
    inventory = get_real_inventory(_uid, supabase) if _uid else []

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

        df_orig = pd.DataFrame(rows)
        df_edit = st.data_editor(
            df_orig,
            column_config={
                "종목명":    st.column_config.TextColumn("종목명",         disabled=True, width="medium"),
                "티커":      st.column_config.TextColumn("야후파이낸스 티커", help="예: 005930.KS / SCHD / AAPL", width="medium"),
                "상태":      st.column_config.TextColumn("현재 상태",       disabled=True, width="small"),
                "보유 수량": st.column_config.NumberColumn("보유 수량",     disabled=True, width="small"),
            },
            use_container_width=True,
            hide_index=True,
            key="ticker_editor",
        )

        if st.button("💾 티커 변경사항 저장", type="primary"):
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

    # 5. 앱 사용 방법 안내
    st.markdown("---")
    st.markdown("#### 📖 사용 방법")
    with st.expander("앱 사용 방법 보기", expanded=False):
        st.info("""
        **1. 데이터 기록 (Track 1)**
        - MTS 매매 내역이나 잔고를 캡처해 올리세요.
        - AI가 종목과 수량을 읽어 데이터로 저장합니다.
        - 장기 투자 성과를 숫자로 확인하세요.
        """)
        st.success("""
        **2. 멘탈 관리 (Track 2)**
        - 시장이 흔들려 불안할 때 태그를 누르세요.
        - "무섭다", "팔고 싶다" 등 짧은 감정을 쓰세요.
        - AI 멘토가 과거 기록을 바탕으로 처방을 내립니다.
        """)
        st.caption("💡 Tip: 매일 사진을 올릴 필요는 없습니다. 매매가 없는 날엔 태그 하나와 짧은 생각만 남겨보세요.")

    # 6. 계정 데이터 영구 삭제
    st.markdown("---")
    st.markdown("<h4 style='color: #E03131;'>⚠️ 계정 데이터 삭제</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color: #8B95A1; font-size: 0.88em;'>이 작업은 복구가 불가능합니다. 신중히 결정해 주세요.</p>", unsafe_allow_html=True)

    with st.expander("🚨 나의 기록 데이터 영구 삭제"):
        st.caption("⚠️ 주의: 일기 및 매매 기록만 삭제됩니다. 계정(이메일/비밀번호)은 유지되므로 같은 계정으로 다시 로그인할 수 있습니다.")
        confirm = st.text_input('본인 확인을 위해 아래 입력창에 "삭제합니다"를 입력해주세요', key="delete_confirm")
        if st.button("💥 내 기록 데이터 영구 삭제", type="primary"):
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
