# 코드 리뷰 보고서 — AI 주식 페이스메이커

> 작성일: 2026-05-19  
> 리뷰 대상: 전체 Python 소스 (14개 파일)

---

## 요약

| 심각도 | 건수 |
|--------|------|
| 🟠 높음 (High) | 3 |
| 🟡 중간 (Medium) | 6 |
| 🔵 낮음 (Low) | 5 |

---

## 🟠 높음 (High)

### 2. XSS 취약점 — AI 생성 HTML 무방비 렌더링

**파일:** [`diary_upload.py:391`](diary_upload.py), [`tab_records.py:83`](tab_records.py)

```python
# diary_upload.py
st.markdown(st.session_state['final_result'], unsafe_allow_html=True)

# tab_records.py
st.markdown(feedback_html, unsafe_allow_html=True)
```

**문제:** AI(Gemini)가 생성한 텍스트를 HTML 이스케이프 없이 그대로 렌더링합니다. 프롬프트 인젝션으로 AI가 `<script>` 태그나 악성 링크를 포함한 응답을 반환하면 브라우저에서 실행됩니다. AI 응답에 HTML 태그를 허용하는 시스템 프롬프트(`[ai_feedback 작성 규칙] HTML 태그를 사용하세요`)가 이 위험을 증폭시킵니다.

**해결:** AI 응답에서 허용할 HTML 태그를 화이트리스트로 제한하거나(예: `bleach` 라이브러리), `unsafe_allow_html=False`로 바꾸고 AI 프롬프트에서 Markdown 형식을 사용하도록 변경합니다.

---

### 3. 인증 토큰 평문 디스크 저장

**파일:** [`session_utils.py:16-23`](session_utils.py)

```python
def save_session_to_disk(session_dict: dict, dev_mode: bool) -> None:
    if not dev_mode:
        return
    SESSION_CACHE_PATH.write_text(json.dumps(session_dict), encoding="utf-8")
```

**문제:** `access_token`과 `refresh_token`이 `.streamlit/session_cache.json`에 평문 JSON으로 저장됩니다. `DEV_MODE`가 활성화된 로컬 환경에서 이 파일이 실수로 git에 커밋되거나 다른 프로그램에 노출되면 계정 탈취가 가능합니다.

**해결:**
- `.streamlit/` 디렉토리를 `.gitignore`에 추가합니다 (secrets.toml 포함).
- 민감도가 낮은 대안으로 `user_id`와 만료 시각만 저장하고, 앱 시작 시 Supabase `refresh_token`으로 재인증하는 방식으로 변경합니다.

---

### 4. 계정 삭제 기능이 인증 레코드를 삭제하지 않음

**파일:** [`tab_settings.py:96-104`](tab_settings.py)

```python
supabase.table("journals").delete().eq("user_id", _uid).execute()
supabase.table("trades").delete().eq("user_id", _uid).execute()
# Supabase auth 계정 자체는 삭제되지 않음
```

**문제:** 사용자는 "모든 정보 영구 삭제"라고 인식하지만, 실제로는 데이터만 지워지고 Supabase Auth의 사용자 계정은 그대로 남습니다. 같은 이메일로 재가입이 불가능하거나 유저 목록에 계속 잔존합니다.

**해결:** Supabase Admin API(`supabase.auth.admin.delete_user(uid)`)를 서버 사이드에서 호출하거나, UI 문구를 "내 기록만 삭제"로 명확히 수정합니다. Streamlit 클라이언트에서는 Admin API 키 노출 위험이 있으므로 Edge Function 또는 별도 백엔드를 경유해야 합니다.

---

## 🟡 중간 (Medium)

### 5. 일기 저장에 오류 처리 없음

**파일:** [`diary_upload.py:361-366`](diary_upload.py)

```python
supabase.table("journals").insert({
    "user_id":     _uid,
    "tags":        tags_str,
    "content":     all_data_str,
    "ai_feedback": ai_feedback,
}).execute()
# 예외 처리 없음 — 저장 실패 시 사용자에게 알리지 않고 진행됨
```

**문제:** trades 저장에는 `try/except`가 있는데 journals 저장에는 없습니다. DB 연결 오류 시 사용자는 저장이 완료된 것으로 착각합니다.

**해결:** journals insert를 `try/except`로 감싸고, 실패 시 `st.session_state['final_error']`에 에러를 기록합니다.

---

### 6. 부분 저장 문제 — 일기는 저장되고 거래 내역은 누락

**파일:** [`diary_upload.py:342-373`](diary_upload.py)

```python
if real_price <= 0:
    st.warning("... 평단가 기록을 건너뜁니다.")
    continue
# ... trades 일부만 insert
supabase.table("journals").insert({...}).execute()  # 항상 저장됨
```

**문제:** 실시간 가격을 가져오지 못한 종목의 거래는 저장 생략 경고를 보여주지만, 일기 자체는 정상 저장됩니다. 그런데 `st.warning`이 `spinner` 블록 안에서 호출되므로 실제로 사용자에게 표시되지 않을 수 있습니다. 나중에 과거 기록을 보면 매매 내역과 일기가 불일치하게 됩니다.

**해결:** 가격 미수신 경고를 spinner 블록 밖으로 이동하거나, 저장 후 요약 화면에서 "N개 종목의 가격을 기록하지 못했습니다"라고 명시합니다.

---

### 7. `None` stock_name이 UI에서 처리되지 않음

**파일:** [`diary_inventory.py:175-178`](diary_inventory.py)

```python
for r in resp.data:
    name = r.get("stock_name")  # None일 수 있음
    amount = float(r.get("dividend_amount") or r.get("quantity") or 0)
    div_by_stock[name] = div_by_stock.get(name, 0) + amount
```

**문제:** `stock_name` 컬럼이 DB에서 NULL이면 `name = None`이 되어 `div_by_stock[None]`에 집계됩니다. 이후 HTML 렌더링 시 종목명 자리에 `None` 문자열이 출력됩니다.

**해결:** `if not name: continue` 조건을 추가합니다.

---

### 8. `get_supabase()` 매 호출마다 새 클라이언트 생성

**파일:** [`app.py:211-228`](app.py)

```python
def get_supabase() -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    # 매 렌더링마다 새 클라이언트 인스턴스 생성
```

**문제:** Streamlit은 매 인터랙션마다 스크립트를 재실행합니다. `get_supabase()`가 호출될 때마다 새 클라이언트를 생성하면 불필요한 초기화 비용이 발생합니다. 또한 `app.py`에서 `supabase = get_supabase()`로 얻은 클라이언트와 각 탭 함수로 전달된 클라이언트가 동일 객체임이 보장되지 않습니다.

**해결:** `@st.cache_resource`로 클라이언트를 캐싱하거나, `st.session_state`에 클라이언트를 저장해 재사용합니다.

---

### 9. AI JSON 파싱 실패 시 "변동 없음"으로 오인

**파일:** [`diary_upload.py:103-109`](diary_upload.py)

```python
try:
    ai_text = st.session_state.get('temp_extracted_data', '{}')
    extracted_dict = json.loads(ai_text.strip())
except Exception as e:
    st.error(f"AI 응답 파싱 실패 ({e}).")
    extracted_dict = {}
# extracted_dict = {} 이면 diff_data = {} → "DB 잔고와 동일합니다" 출력
```

**문제:** AI가 잘못된 JSON을 반환하면 `extracted_dict`가 빈 딕셔너리가 되고, 이어지는 비교에서 변동이 없다고 표시됩니다. 오류 메시지(`st.error`)와 성공 메시지("DB 잔고와 동일합니다")가 동시에 표시되어 혼란을 줍니다.

**해결:** `extracted_dict = {}`인 경우 diff 계산을 건너뛰고 에러 상태를 유지하도록 분기 처리합니다.

---

### 10. `calculate_scores`의 UI 호출 (`st.sidebar.warning`)이 함수 내부에 있음

**파일:** [`db.py:51-52`](db.py)

```python
except Exception as e:
    st.sidebar.warning(f"점수 조회 실패: {e}")
```

**문제:** `db.py`는 데이터 레이어인데 UI(`st.sidebar`)를 직접 호출합니다. 이 함수를 비-Streamlit 환경(테스트, CLI)에서 사용하면 `streamlit.errors.StreamlitAPIException`이 발생합니다. 관심사 분리 원칙에 위배됩니다.

**해결:** 예외를 그대로 올리거나 `logging.warning`으로 대체하고, 호출부(`tab_diary.py`)에서 UI 처리를 담당하도록 합니다.

---

## 🔵 낮음 (Low)

### 11. `get_recent_journals` TTL이 10초로 너무 짧음

**파일:** [`db.py:139`](db.py)

```python
@st.cache_data(ttl=10)
def get_recent_journals(user_id: str, _supabase, limit: int = 50):
```

**문제:** 10초마다 캐시가 무효화되어 매 탭 전환마다 DB 조회가 발생합니다. 사용자가 탭 사이를 빠르게 오가면 불필요한 쿼리가 다수 발생합니다.

**해결:** 저장 직후 `.clear()`를 호출하는 현재 패턴이 이미 있으므로, TTL을 60~300초로 늘려도 안전합니다.

---

### 12. 환율 기본값이 하드코딩됨

**파일:** [`prices.py:130-136`](prices.py)

```python
def get_usd_to_krw(time_bucket: str = "") -> float:
    ...
    return 1380.0  # 실패 시 폴백값
```

**문제:** yfinance 조회 실패 시 1,380원을 반환합니다. 실제 환율과 크게 차이 날 경우 USD 보유 종목의 총 평가금액 계산이 크게 틀릴 수 있습니다.

**해결:** 마지막으로 성공한 환율을 `st.session_state`에 캐싱하여 폴백값으로 사용합니다.

---

### 14. 로그아웃 시 작업 중인 데이터 경고 없음

**파일:** [`app.py:265-268`](app.py)

```python
if st.sidebar.button("🚪 로그아웃"):
    clear_session_from_disk()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
```

**문제:** 4단계 입력 흐름 중 어디서든 로그아웃 버튼을 누르면 입력 중인 데이터가 경고 없이 사라집니다. `daily_stock_list`에 데이터가 있는 경우 특히 위험합니다.

**해결:** `st.session_state.get('daily_stock_list')` 또는 `current_step != 'upload_mode'`일 때 확인 다이얼로그를 표시합니다.

---

### 15. `TAG_SALARY_BUY`와 `TAG_IMPULSE_TRADE`가 같은 이모지 사용

**파일:** [`constants.py:2,8`](constants.py)

```python
TAG_SALARY_BUY    = "💸 #월급날정기매수"
TAG_IMPULSE_TRADE = "💸 #뇌동매매반성"
```

**문제:** 두 태그가 모두 `💸` 이모지를 사용해 시각적으로 구분이 어렵습니다. 긍정적 루틴 태그와 반성 태그가 같은 아이콘을 공유하면 UX가 직관적이지 않습니다.

**해결:** `TAG_IMPULSE_TRADE`의 이모지를 `🚨` 또는 `⚠️`으로 변경합니다.

---

## 기타 개선 제안

- **비밀번호 찾기 OTP 타입**: `auth.py:115`에서 `"type": "email"`을 사용하는데, 비밀번호 재설정 목적이라면 Supabase 문서 기준 `"type": "recovery"`가 더 명확합니다. 현재 동작은 OTP 로그인 방식으로 처리되어 실제로 작동하나, 의도가 불명확합니다.

- **`TICKER_MAP` 관리**: `prices.py`의 `TICKER_MAP`에 없는 종목은 실시간 가격이 조회되지 않아 "티커 미등록"으로 표시됩니다. 사용자가 직접 추가할 수 없는 구조이므로, DB에 ticker 컬럼을 추가해 동적으로 관리하거나 별도 설정 화면을 제공하는 것을 권장합니다.

- **AI 응답 속도**: `diary_upload.py`의 최종 분석은 `spinner` 안에서 동기적으로 실행됩니다. 응답이 느릴 경우 사용자가 앱이 멈춘 것으로 오인할 수 있습니다. Streamlit의 `st.status`를 활용해 단계별 진행 상황을 표시하면 UX가 개선됩니다.
