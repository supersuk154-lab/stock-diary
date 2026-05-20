import re
import streamlit as st
import datetime
from app_constants import KST


def _sanitize_report_html(html_content: str) -> str:
    """리포트 HTML에서 XSS 벡터만 제거 (서식·스타일은 유지).
    - <script> 블록 완전 제거
    - on* 이벤트 핸들러 속성 제거 (onerror, onclick, onload 등)
    - javascript: URL 제거
    """
    # <script>...</script> 블록 제거
    html_content = re.sub(
        r'<script\b[^>]*>.*?</script>',
        '',
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # on* 이벤트 핸들러 속성 제거
    html_content = re.sub(
        r'\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]*)',
        '',
        html_content,
        flags=re.IGNORECASE,
    )
    # javascript: URL 제거
    html_content = re.sub(
        r'(href|src)\s*=\s*["\']?\s*javascript\s*:',
        r'\1="#"',
        html_content,
        flags=re.IGNORECASE,
    )
    return html_content


def _is_admin(supabase, secrets) -> bool:
    """관리자 여부를 Supabase JWT에서 직접 검증 (session_state 우회 방지)."""
    try:
        user_resp = supabase.auth.get_user()
        email = user_resp.user.email if (user_resp and user_resp.user) else ""
    except Exception:
        return False
    if not email:
        return False
    admin_emails = secrets.get("ADMIN_EMAILS", None)
    if admin_emails is not None:
        return email in list(admin_emails)
    admin_email = secrets.get("ADMIN_EMAIL", "")
    return bool(admin_email) and email == admin_email


def _get_latest_report(supabase):
    try:
        resp = (
            supabase.table("daily_reports")
            .select("id, created_at, title, html_content")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        st.error(f"리포트 불러오기 실패: {e}")
        return None


@st.cache_data(ttl=600)
def _get_report_list(_supabase, limit: int = 20):
    try:
        resp = (
            _supabase.table("daily_reports")
            .select("id, created_at, title")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        st.error(f"리포트 목록 조회 실패: {e}")
        return []


@st.cache_data(ttl=600)
def _get_report_by_id(_supabase, report_id: int):
    try:
        resp = (
            _supabase.table("daily_reports")
            .select("id, created_at, title, html_content")
            .eq("id", report_id)
            .single()
            .execute()
        )
        return resp.data
    except Exception as e:
        st.error(f"리포트 조회 실패: {e}")
        return None


def _format_kst(iso_ts: str) -> str:
    if not iso_ts:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M")
    except Exception:
        return iso_ts


import streamlit.components.v1 as components
def _render_report_html(html_content: str, height: int = 1800):
    components.html(html_content, height=height, scrolling=True)


def render_report_tab(supabase, secrets):
    is_admin = _is_admin(supabase, secrets)

    if is_admin:
        _render_admin_section(supabase)
        st.markdown("---")

    _render_viewer_section(supabase)


def _render_admin_section(supabase):
    with st.expander("🔐 관리자 — 리포트 업로드", expanded=False):
        uploaded_file = st.file_uploader(
            "오늘의 투자 리포트 HTML 파일을 업로드하세요",
            type=["html"],
            key="report_uploader",
        )

        if uploaded_file is not None:
            html_bytes = uploaded_file.read()
            html_content = html_bytes.decode("utf-8")
            title = uploaded_file.name.replace(".html", "")

            st.caption(f"파일명: `{uploaded_file.name}` ({len(html_bytes):,} bytes)")

            with st.expander("미리보기", expanded=False):
                _render_report_html(html_content, height=600)

            if st.button("Supabase에 저장", type="primary", key="upload_report_btn"):
                try:
                    supabase.table("daily_reports").insert({
                        "title": title,
                        "html_content": _sanitize_report_html(html_content),
                        "uploaded_by": st.session_state.get("user_email", ""),
                    }).execute()
                    st.success(f"✅ 리포트 저장 완료: **{title}**")
                    _get_report_list.clear()
                    _get_report_by_id.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")


def _render_viewer_section(supabase):
    st.markdown("### 📰 오늘의 투자 리포트")

    reports = _get_report_list(supabase)

    if not reports:
        st.info("아직 업로드된 리포트가 없습니다.")
        return

    latest = reports[0]
    st.caption(f"최신 리포트: **{latest['title']}** ({_format_kst(latest['created_at'])})")

    if len(reports) > 1:
        options = {r["id"]: f"{r['title']} ({_format_kst(r['created_at'])})" for r in reports}
        selected_id = st.selectbox(
            "과거 리포트 보기",
            options=list(options.keys()),
            format_func=lambda x: options[x],
            key="report_selector",
        )
        report = _get_report_by_id(supabase, selected_id)
    else:
        report = _get_report_by_id(supabase, latest["id"])

    if report:
        _render_report_html(report["html_content"], height=1800)
