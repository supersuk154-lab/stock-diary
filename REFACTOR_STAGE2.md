# 2단계 모듈 분리 가이드

1단계에서 `prices.py` / `ai_helper.py` / `db.py`를 분리했다.  
2단계는 `ui_components.py`와 `auth.py` 분리다.

---

## 현재 파일 구조 (1단계 완료 후)

```
app.py          — UI + 인증 + 라우팅  (1,278줄)
prices.py       — yfinance, 환율, TICKER_MAP
ai_helper.py    — safe_generate
db.py           — Supabase 쿼리 함수
```

---

## STEP A: ui_components.py 분리 (난이도 ★☆☆)

### 분리할 대상

`app.py` 안의 `render_radar_chart()` 함수 (약 30줄).

### 방법

**1. `ui_components.py` 파일 생성**

```python
# ui_components.py
import plotly.graph_objects as go


def render_radar_chart(scores: dict):
    categories = list(scores.keys())
    values = list(scores.values())
    categories.append(categories[0])
    values.append(values[0])

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        line_color='#d9f99d',
        fillcolor='rgba(217, 249, 157, 0.4)'
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color='gray',
                            gridcolor='rgba(255,255,255,0.2)'),
            angularaxis=dict(tickfont=dict(size=12)),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=55, r=55, t=40, b=40),
        showlegend=False,
        height=320
    )
    return fig
```

**2. app.py 수정 (2곳)**

상단 import에 추가:
```python
from ui_components import render_radar_chart
```

app.py 안의 `render_radar_chart` 함수 정의 블록을 통째로 삭제.  
호출부(`render_radar_chart(current_scores)`)는 그대로 두면 됨.

**3. 확인**
```bash
python -c "import ast; ast.parse(open('ui_components.py', encoding='utf-8').read()); print('OK')"
python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('OK')"
```

---

## STEP B: auth.py 분리 (난이도 ★★★)

### 왜 어려운가

`show_login()`이 app.py 안의 세 함수를 직접 호출한다:

| 호출 | 정의 위치 |
|------|-----------|
| `save_session_to_disk()` | app.py |
| `create_client()` | supabase 라이브러리 (OK) |
| `st.rerun()` | streamlit (OK) |

`save_session_to_disk()`가 app.py에 있기 때문에, `auth.py`가 app.py를 import하면 **순환 참조**가 발생한다.

### 해결 전략: session_utils.py 먼저 분리

`save_session_to_disk`, `load_session_from_disk`, `clear_session_from_disk`, `SESSION_CACHE_PATH`, `DEV_MODE` 관련 코드를 별도 파일로 먼저 뺀다.

**순서**

```
1. session_utils.py 생성
2. auth.py 생성
3. app.py에서 두 파일 import
```

---

### session_utils.py 만들기

app.py에서 아래 코드를 그대로 옮긴다 (260~317줄 근방):

```python
# session_utils.py
import json
import os
from pathlib import Path


SESSION_CACHE_PATH = Path(".streamlit") / "session_cache.json"


def get_dev_mode(secrets) -> bool:
    """Streamlit Cloud 환경에서는 자동으로 비활성화."""
    return (
        secrets.get("DEV_MODE", False)
        and not os.environ.get("STREAMLIT_SERVER_HEADLESS")
    )


def save_session_to_disk(session_dict: dict, dev_mode: bool) -> None:
    if not dev_mode:
        return
    try:
        SESSION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_CACHE_PATH.write_text(json.dumps(session_dict), encoding="utf-8")
    except Exception:
        pass


def load_session_from_disk(dev_mode: bool) -> dict | None:
    if not dev_mode:
        return None
    try:
        if SESSION_CACHE_PATH.exists():
            return json.loads(SESSION_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def clear_session_from_disk() -> None:
    try:
        if SESSION_CACHE_PATH.exists():
            SESSION_CACHE_PATH.unlink()
    except Exception:
        pass
```

> **주의**: 현재 app.py의 `save_session_to_disk(session_dict)`는 인자가 1개인데,  
> 여기서는 `dev_mode`를 추가 인자로 받도록 바꿨다.  
> app.py 호출부도 `save_session_to_disk(session_dict, DEV_MODE)` 로 함께 수정해야 한다.

---

### auth.py 만들기

```python
# auth.py
import streamlit as st
from supabase import create_client
from session_utils import save_session_to_disk


def show_login(supabase_url: str, supabase_anon_key: str, dev_mode: bool) -> None:
    """로그인/회원가입 UI. 성공 시 st.session_state에 세션 저장 후 st.rerun()."""
    st.title("📈 AI 주식 페이스메이커")
    st.markdown("### 🔐 로그인")
    st.caption("이메일과 비밀번호를 입력해주세요. 처음 오신 분은 회원가입을 눌러주세요.")

    with st.form("login_form"):
        st.markdown("#### 로그인")
        email = st.text_input("이메일", placeholder="you@example.com")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        login_btn = st.form_submit_button("✅ 로그인", type="primary", use_container_width=True)

    if login_btn:
        if not email or not password:
            st.warning("이메일과 비밀번호를 모두 입력해주세요.")
        else:
            try:
                client = create_client(supabase_url, supabase_anon_key)
                response = client.auth.sign_in_with_password({
                    "email": email,
                    "password": password,
                })
                if response.session:
                    st.session_state["supabase_session"] = {
                        "access_token": response.session.access_token,
                        "refresh_token": response.session.refresh_token,
                    }
                    st.session_state["user_id"] = response.user.id
                    st.session_state["user_email"] = response.user.email
                    save_session_to_disk(st.session_state["supabase_session"], dev_mode)
                    st.rerun()
            except Exception:
                st.error("⚠️ 로그인 실패: 이메일이나 비밀번호를 다시 확인해주세요.")

    st.markdown("---")

    with st.expander("📝 처음 오셨나요? 회원가입"):
        with st.form("signup_form"):
            su_email = st.text_input("이메일", placeholder="you@example.com", key="su_email")
            su_password = st.text_input("비밀번호", type="password", placeholder="6자리 이상", key="su_pw")
            su_password2 = st.text_input("비밀번호 확인", type="password",
                                         placeholder="비밀번호를 한 번 더 입력하세요", key="su_pw2")
            signup_btn = st.form_submit_button("🎉 회원가입", type="primary", use_container_width=True)

    if signup_btn:
        if not su_email or not su_password or not su_password2:
            st.warning("모든 항목을 입력해주세요.")
        elif su_password != su_password2:
            st.error("❌ 비밀번호가 일치하지 않습니다. 다시 확인해주세요.")
        elif len(su_password) < 6:
            st.warning("비밀번호는 6자리 이상으로 설정해주세요.")
        else:
            try:
                client = create_client(supabase_url, supabase_anon_key)
                client.auth.sign_up({"email": su_email, "password": su_password})
                st.success("🎉 회원가입 완료! 위 로그인 폼에서 로그인해주세요.")
            except Exception as e:
                st.error(f"⚠️ 회원가입 실패: {e}")
```

---

### app.py 수정 포인트

**import 추가:**
```python
from session_utils import (
    SESSION_CACHE_PATH, get_dev_mode,
    save_session_to_disk, load_session_from_disk, clear_session_from_disk,
)
from auth import show_login
```

**DEV_MODE 선언 변경:**
```python
# 기존
DEV_MODE = (
    st.secrets.get("DEV_MODE", False)
    and not os.environ.get("STREAMLIT_SERVER_HEADLESS")
)

# 변경 후
DEV_MODE = get_dev_mode(st.secrets)
```

**`save_session_to_disk` 호출부 3곳 수정:**
```python
# 기존
save_session_to_disk(st.session_state["supabase_session"])

# 변경 후
save_session_to_disk(st.session_state["supabase_session"], DEV_MODE)
```

**`show_login` 호출부 변경:**
```python
# 기존
show_login()

# 변경 후
show_login(SUPABASE_URL, SUPABASE_ANON_KEY, DEV_MODE)
```

**app.py에서 삭제할 코드:**
- `SESSION_CACHE_PATH` 선언
- `save_session_to_disk()` 함수 정의
- `load_session_from_disk()` 함수 정의
- `clear_session_from_disk()` 함수 정의
- `show_login()` 함수 정의 (341~409줄 근방)

---

## 완료 후 최종 구조

```
app.py              — 탭 UI + 라우팅만 (목표 ~800줄)
prices.py           — yfinance, 환율, TICKER_MAP
ai_helper.py        — safe_generate
db.py               — Supabase 쿼리 함수
session_utils.py    — 디스크 세션 저장/로드/삭제, DEV_MODE
auth.py             — 로그인, 회원가입 UI
ui_components.py    — render_radar_chart
```

---

## 검증 체크리스트

분리 후 아래를 순서대로 확인한다.

- [ ] 모든 `.py` 파일에서 `python -c "import ast; ast.parse(...)"` 통과
- [ ] `streamlit run app.py` 실행 후 에러 없이 로그인 화면 뜨는지
- [ ] 로그인 → 탭1 보물함 로드 → 이미지 업로드 → 최종 분석 저장 흐름 한 번 돌려보기
- [ ] `DEV_MODE = true`일 때 로그아웃 후 재실행 시 자동 로그인 유지 확인
- [ ] Streamlit Cloud 배포 환경에서 `DEV_MODE` 자동 비활성화 확인
  (`STREAMLIT_SERVER_HEADLESS=1` 환경변수로 로컬 시뮬레이션 가능)
