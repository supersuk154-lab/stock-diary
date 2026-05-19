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

    with st.expander("📖 티커 찾는 방법 — 미장 / 국장 / 한국 ETF 완전 매뉴얼", expanded=False):
        st.markdown("#### 야후파이낸스 티커란?")
        st.markdown(
            "이 앱은 **Yahoo Finance API**로 실시간 가격을 가져옵니다. "
            "따라서 내 종목의 야후파이낸스 티커 코드를 정확히 입력해야 가격이 표시됩니다. "
            "아래 시장별 안내를 따라 티커를 찾아보세요."
        )

        st.markdown("---")

        # ── 미국 주식 ──────────────────────────────────────────
        st.markdown("##### 🇺🇸 미장 (미국 주식 · 미국 ETF)")
        col_us1, col_us2 = st.columns([1, 1])
        with col_us1:
            st.info(
                "**형식:** 영문 심볼 그대로 입력\n\n"
                "```\n"
                "애플        → AAPL\n"
                "엔비디아     → NVDA\n"
                "마이크로소프트 → MSFT\n"
                "테슬라       → TSLA\n"
                "버크셔(B)    → BRK-B\n"
                "```\n\n"
                "**미국 ETF:**\n"
                "```\n"
                "S&P500      → VOO  또는 SPY\n"
                "나스닥100   → QQQ\n"
                "배당성장     → SCHD\n"
                "커버드콜     → JEPI\n"
                "월배당      → QYLD\n"
                "```"
            )
        with col_us2:
            st.success(
                "**어디서 찾나요?**\n\n"
                "**방법 ①** Yahoo Finance 직접 검색\n"
                "1. [finance.yahoo.com](https://finance.yahoo.com) 접속\n"
                "2. 검색창에 종목명 입력 (영문 권장)\n"
                "3. URL의 `/quote/XXXX` 부분이 티커\n\n"
                "**방법 ②** ETF.com (ETF 전용)\n"
                "- [etf.com](https://www.etf.com) 에서 ETF 검색\n"
                "- 티커가 크게 표시됨\n\n"
                "**방법 ③** 자동 연결 활용\n"
                "- 영문 1~5자리 심볼은 **앱이 자동 연결**\n"
                "- 자동 매칭 버튼 먼저 눌러보세요!"
            )

        st.markdown("---")

        # ── 한국 주식 ──────────────────────────────────────────
        st.markdown("##### 🇰🇷 국장 (한국 주식)")
        col_kr1, col_kr2 = st.columns([1, 1])
        with col_kr1:
            st.info(
                "**형식:** `종목코드6자리` + `.KS` 또는 `.KQ`\n\n"
                "```\n"
                "KOSPI 종목 → 숫자6자리.KS\n"
                "  삼성전자   → 005930.KS\n"
                "  SK하이닉스 → 000660.KS\n"
                "  카카오     → 035720.KS\n"
                "  LG에너지솔루션 → 373220.KS\n\n"
                "KOSDAQ 종목 → 숫자6자리.KQ\n"
                "  에코프로   → 086520.KQ\n"
                "  알테오젠   → 196170.KQ\n"
                "  HLB      → 028300.KQ\n"
                "```"
            )
        with col_kr2:
            st.success(
                "**어디서 종목코드 6자리를 찾나요?**\n\n"
                "**방법 ①** 네이버페이 증권 (가장 쉬움)\n"
                "1. [finance.naver.com](https://finance.naver.com) 접속\n"
                "2. 종목 검색 후 클릭\n"
                "3. URL의 숫자 6자리가 종목코드\n"
                "   예) `/item/main.naver?code=005930`\n\n"
                "**방법 ②** 한국거래소 (KRX)\n"
                "1. [data.krx.co.kr](https://data.krx.co.kr) 접속\n"
                "2. 기본통계 → 주식 → 종목검색\n"
                "3. 종목코드 6자리 확인\n\n"
                "**방법 ③** MTS 앱\n"
                "- 보유 종목 상세에서 종목코드 확인 가능"
            )

        st.markdown("---")

        # ── 한국 ETF ──────────────────────────────────────────
        st.markdown("##### 🏦 한국 ETF (KODEX, TIGER, ACE 등)")
        col_etf1, col_etf2 = st.columns([1, 1])
        with col_etf1:
            st.info(
                "**형식:** `ETF코드6자리.KS` (대부분 KOSPI 상장)\n\n"
                "```\n"
                "KODEX 200       → 069500.KS\n"
                "KODEX 삼성그룹  → 102780.KS\n"
                "TIGER 미국S&P500 → 360750.KS\n"
                "TIGER 미국나스닥100 → 133690.KS\n"
                "ACE 미국배당다우존스 → 402970.KS\n"
                "KODEX 배당성장   → 211560.KS\n"
                "TIGER 차이나CSI300 → 192090.KS\n"
                "```\n\n"
                "KOSDAQ 상장 ETF는 드물지만 `.KQ` 사용"
            )
        with col_etf2:
            st.success(
                "**어디서 한국 ETF 코드를 찾나요?**\n\n"
                "**방법 ①** 네이버페이 증권 ETF 탭 (추천)\n"
                "1. [finance.naver.com/fund/etf](https://finance.naver.com/fund/etfItemList.naver) 접속\n"
                "2. ETF명 검색 후 클릭\n"
                "3. URL에서 6자리 코드 확인 후 `.KS` 붙이기\n\n"
                "**방법 ②** 한국거래소 ETF 정보\n"
                "1. [etf.krx.co.kr](https://etf.krx.co.kr) 접속\n"
                "2. ETF명 검색 → 종목코드 확인\n\n"
                "**방법 ③** 자동 매칭 버튼 활용\n"
                "- KODEX, TIGER 등 유명 ETF는\n"
                "  **자동 매칭으로 연결**되는 경우 많음\n"
                "- 자동 매칭 먼저 시도해 보세요!"
            )

        st.markdown("---")
        st.warning(
            "**주의사항**\n\n"
            "- 티커를 잘못 입력하면 엉뚱한 종목 가격이 표시됩니다.\n"
            "- 저장 전 Yahoo Finance에서 해당 티커로 검색해 맞는지 꼭 확인하세요.\n"
            "- 보물함에서 가격이 뜨지 않으면 티커가 잘못된 겁니다 (빈칸으로 다시 저장하면 초기화)."
        )

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
                use_container_width=True,
                help="미연결 종목의 티커를 KRX 데이터베이스와 야후파이낸스 규칙으로 자동으로 찾아 저장합니다.",
            )
        with col_dl:
            # CSV 다운로드 — 현재 티커 상태 전체 내보내기
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
                use_container_width=True,
                help="종목명·티커 목록을 CSV로 받아 엑셀에서 편집한 뒤 아래 업로드 버튼으로 올리세요.",
            )
        with col_info:
            st.caption("⚡ 자동 매칭은 미연결(⚠️) 종목만 · CSV로 일괄 수정도 가능합니다.")

        # ── CSV 업로드 (일괄 티커 등록) ─────────────────────
        with st.expander("CSV 파일로 티커 일괄 등록", expanded=False):
            st.markdown(
                "**사용법**\n"
                "1. 위 **CSV 다운로드** 버튼으로 현재 목록을 내려받습니다.\n"
                "2. 엑셀(또는 구글 시트)로 열어 `야후파이낸스_티커` 열을 채웁니다.\n"
                "3. CSV로 저장한 뒤 아래에 업로드하면 자동으로 반영됩니다.\n\n"
                "형식: `종목명` 열이 기준 키입니다. 종목명이 정확히 일치해야 저장됩니다."
            )
            uploaded_csv = st.file_uploader(
                "티커가 입력된 CSV 파일을 업로드하세요",
                type=["csv"],
                key="ticker_csv_uploader",
            )
            if uploaded_csv is not None:
                try:
                    import io as _io2
                    _up_df = pd.read_csv(_io2.BytesIO(uploaded_csv.read()))
                    # 컬럼 이름 정규화
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
            use_container_width=True,
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
