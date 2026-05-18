# AI 주식 다이어리 — 수정 지시서

> 이 문서는 다른 AI가 수정 작업을 수행하기 위한 지시서입니다.
> 프로젝트 루트: `stock-diary/`
> 아래 수정 사항을 **순서대로** 진행하세요.

---

## ✅ 이미 수정 완료된 항목 (건드리지 마세요)

- `tab_diary.py` — `get_daily_meal()` 함수 구현 완료
- `tab_diary.py` — 고아 코드(dead code) 23~34번째 라인 제거 완료
- `tab_diary.py` — `safe_generate()` 호출 3곳에 `client=ai_client, model_name=MODEL_NAME` 인자 추가 완료
- `tab_diary.py` — `MODEL_NAME` 상수 추가 완료

---

## 🔴 즉시 수정 필수 — 보안 취약점 (user_id 필터 누락)

### 문제 설명

`db.py`의 DB 조회 함수들이 `user_id`를 파라미터로 받고 있지만,
실제 Supabase 쿼리에 `.eq("user_id", user_id)` 조건을 **추가하지 않아**
다른 사용자의 데이터까지 전부 긁어옵니다.

Supabase RLS(Row Level Security)가 올바르게 설정되어 있으면 서버에서 막히겠지만,
RLS 설정 오류나 변경 시 즉시 데이터 유출로 이어지는 구조입니다.
코드 레벨에서도 명시적으로 필터링하는 것이 안전합니다.

---

### 수정 1: `db.py` — `get_real_inventory()`

**파일**: `stock-diary/db.py`
**함수**: `get_real_inventory(user_id: str, _supabase)` (약 150번째 줄)

**현재 코드:**
```python
response = (
    _supabase.table("trades")
    .select("stock_name, quantity, price, currency, type")
    .neq("type", "dividend")
    .execute()
)
```

**수정 후 코드:**
```python
response = (
    _supabase.table("trades")
    .select("stock_name, quantity, price, currency, type")
    .eq("user_id", user_id)
    .neq("type", "dividend")
    .execute()
)
```

---

### 수정 2: `db.py` — `get_dividend_total()`

**파일**: `stock-diary/db.py`
**함수**: `get_dividend_total(user_id: str, _supabase)` (약 202번째 줄)

**현재 코드:**
```python
response = (
    _supabase.table("trades")
    .select("quantity, dividend_amount, currency")
    .eq("type", "dividend")
    .execute()
)
```

**수정 후 코드:**
```python
response = (
    _supabase.table("trades")
    .select("quantity, dividend_amount, currency")
    .eq("user_id", user_id)
    .eq("type", "dividend")
    .execute()
)
```

---

### 수정 3: `db.py` — `get_recent_journals()`

**파일**: `stock-diary/db.py`
**함수**: `get_recent_journals(user_id: str, _supabase, limit: int = 50)` (약 132번째 줄)

**현재 코드:**
```python
response = (
    _supabase.table("journals")
    .select("id, created_at, tags, content, ai_feedback")
    .order("created_at", desc=True)
    .limit(limit)
    .execute()
)
```

**수정 후 코드:**
```python
response = (
    _supabase.table("journals")
    .select("id, created_at, tags, content, ai_feedback")
    .eq("user_id", user_id)
    .order("created_at", desc=True)
    .limit(limit)
    .execute()
)
```

---

### 수정 4: `db.py` — `get_past_context()`

**파일**: `stock-diary/db.py`
**함수**: `get_past_context(tags, supabase)` (약 93번째 줄)

이 함수는 `user_id`를 파라미터로 받지도 않아서 함수 시그니처부터 수정이 필요합니다.

**현재 함수 시그니처:**
```python
def get_past_context(tags, supabase):
```

**수정 후 함수 시그니처:**
```python
def get_past_context(tags, supabase, user_id: str = ""):
```

**현재 쿼리 코드:**
```python
response = (
    supabase.table("journals")
    .select("created_at, content")
    .like("tags", f"%{core_tag}%")
    .order("created_at", desc=True)
    .limit(3)
    .execute()
)
```

**수정 후 코드:**
```python
query = (
    supabase.table("journals")
    .select("created_at, content")
    .like("tags", f"%{core_tag}%")
    .order("created_at", desc=True)
    .limit(3)
)
if user_id:
    query = query.eq("user_id", user_id)
response = query.execute()
```

그리고 `db.py`의 `__all__` 리스트에서 시그니처가 바뀐 것을 반영하세요 (export 목록 자체는 유지).

**`tab_diary.py`에서 호출하는 부분도 수정 필요:**

`tab_diary.py`에서 `get_past_context`를 호출하는 줄을 찾아서:

**현재:**
```python
past_records = get_past_context(selected_tags, supabase)
```

**수정 후:**
```python
past_records = get_past_context(selected_tags, supabase, st.session_state.get("user_id", ""))
```

---

## 🟡 중요 수정 — 계정 삭제 후 세션 클리어 누락

### 수정 5: `tab_settings.py` — 계정 삭제 후 로그아웃 처리

**파일**: `stock-diary/tab_settings.py`
**위치**: `render_settings_tab()` 함수 안, 계정 삭제 성공 블록 (약 93~101번째 줄)

**문제**: 데이터를 DB에서 삭제한 뒤 `st.rerun()`만 호출해서 세션이 그대로 남아있습니다.
세션이 살아있으면 삭제 후에도 로그인 상태로 유지됩니다.

**현재 코드:**
```python
if confirm == "삭제합니다":
    try:
        _uid = st.session_state["user_id"]
        supabase.table("journals").delete().eq("user_id", _uid).execute()
        supabase.table("trades").delete().eq("user_id", _uid).execute()
        get_recent_journals.clear()
        get_real_inventory.clear()
        banner("모든 기록이 영구적으로 안전하게 삭제되었습니다. 초기 화면으로 이동합니다.", type="success")
        st.rerun()
    except Exception as e:
        banner(f"삭제에 실패했습니다: {e}", type="error")
```

**수정 후 코드:**
```python
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
```

> **주의**: `banner()` 호출은 세션 클리어 전에 표시해도 `st.rerun()`으로 화면이 리셋되기 때문에 보이지 않습니다.
> 삭제 성공 메시지는 로그인 화면에서 `st.session_state`의 임시 플래그로 띄우거나 생략하세요.

---

## 🟢 선택적 개선 사항 (우선순위 낮음)

아래는 지금 당장 앱이 터지는 문제는 아니지만, 코드 품질 향상을 위해 권장하는 작업입니다.
여유가 있을 때 진행하세요.

### A. `tab_diary.py` 분리 (대형 리팩토링)

현재 `tab_diary.py`는 1,000줄 이상의 거대한 파일입니다.
아래 3개 파일로 분리하면 유지보수가 쉬워집니다.

| 분리할 파일 | 담당 함수/기능 |
|---|---|
| `diary_inventory.py` | `get_dividend_work_stats`, `render_fire_countdown`, `render_family_contributions`, 보물함 섹션 |
| `diary_chat.py` | AI 멘토 채팅 섹션 |
| `diary_upload.py` | 이미지 업로드 → 데이터 검증 → 최종 분석 섹션 |

`tab_diary.py`는 이 3개를 import해서 조립하는 얇은 진입점으로만 남깁니다.

### B. 태그 문자열 상수화

`db.py`, `tab_diary.py` 곳곳에 `"#월급날정기매수"`, `"#배당금달달해"` 같은 태그 문자열이 하드코딩되어 있습니다.
`constants.py` 파일을 새로 만들어 중앙 관리하세요.

**예시 `constants.py`:**
```python
# 루틴 태그
TAG_SALARY_BUY    = "💸 #월급날정기매수"
TAG_DIVIDEND      = "🍯 #배당금달달해"
TAG_PRAISE_PAST   = "🎯 #과거의나칭찬해"

# 방어 태그
TAG_HOLD          = "🧘‍♂️ #존버는승리한다"
TAG_DIDNT_CHECK   = "🙈 #오늘은안봤다"
TAG_TAKE_BREAK    = "☕ #한템포쉬어가기"

# 감정/반성 태그
TAG_SHAKY         = "😱 #오늘좀흔들"
TAG_IMPULSE_TRADE = "💸 #뇌동매매반성"
TAG_MISTAKE       = "📝 #오늘의실수"

# 멘토 옵션
MENTOR_OPTIONS = [
    "🤖 정중한 AI 비서 (기본/깔끔)",
    "☕ 따뜻한 심리 상담가 (공감/위로)",
    "🤝 다정한 주식 찐친 (유쾌한 반말)",
    "🧊 팩트폭행 1타 강사 (단호/원칙)",
]
```

### C. 불필요한 파일 삭제

아래 파일들은 실제 앱 구동에 사용되지 않습니다. Git 히스토리에는 남아있으니 워킹 디렉토리에서 삭제하세요.

```
stock-diary/app_old.py   ← 깨진 UTF-16LE 파일, 구버전
stock-diary/fix.py       ← tab_diary.py를 직접 덮어쓰는 임시 스크립트
```

---

## 수정 우선순위 요약

| 우선순위 | 항목 | 파일 |
|---|---|---|
| 🔴 1순위 | `get_real_inventory` user_id 필터 추가 | `db.py` |
| 🔴 1순위 | `get_dividend_total` user_id 필터 추가 | `db.py` |
| 🔴 1순위 | `get_recent_journals` user_id 필터 추가 | `db.py` |
| 🔴 1순위 | `get_past_context` user_id 파라미터 추가 + 필터 적용 | `db.py` + `tab_diary.py` |
| 🟡 2순위 | 계정 삭제 후 세션 클리어 | `tab_settings.py` |
| 🟢 3순위 | `tab_diary.py` 파일 분리 | 리팩토링 |
| 🟢 3순위 | 태그 문자열 `constants.py`로 이전 | 새 파일 생성 |
| 🟢 3순위 | `app_old.py`, `fix.py` 삭제 | — |
