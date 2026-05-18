# AI 주식 다이어리 — 수정 지시서 v2

> 이 문서는 외부 AI 리뷰 보고서의 주장을 실제 코드와 대조·검증한 후 작성한 수정 지시서입니다.
> 아래에 없는 항목은 **허위/오판단**으로 확인되어 제외했습니다.
> 프로젝트 루트: `stock-diary/`

---


## 🔴 수정 1 — `supabase_schema.sql` dividend_amount 컬럼 누락 (앱 크래시)

### 문제

`trades` 테이블에 `dividend_amount` 컬럼이 없습니다.
`supabase_schema.sql`의 `trades` 테이블 정의(63~72번째 줄)에 해당 컬럼이 없음:

```sql
create table if not exists trades (
  id bigserial primary key,
  user_id uuid ...,
  created_at timestamptz ...,
  stock_name text not null,
  quantity float not null default 0,
  price float not null default 0,
  currency text not null default 'KRW',
  type text not null default 'buy'
  -- ← dividend_amount 없음
);
```

앱에서는 배당금 저장 시 이 컬럼에 데이터를 씁니다:
```python
supabase.table("trades").insert({
    "dividend_amount": div_amount   # ← 컬럼이 없으므로 PostgreSQL 오류 발생
}).execute()
```

### 수정

**파일**: `stock-diary/supabase_schema.sql`

`trades` 테이블 생성 블록(71번째 줄) `type` 컬럼 정의 바로 다음에 추가:

**현재 코드:**
```sql
  type text not null default 'buy'  -- 'buy' | 'sell' | 'dividend'
);
```

**수정 후:**
```sql
  type text not null default 'buy',  -- 'buy' | 'sell' | 'dividend'
  dividend_amount float              -- 배당금 금액 (type='dividend'일 때 사용)
);
```

그리고 파일 하단 주석 위에 기존 DB에 컬럼 추가하는 ALTER 문도 추가:

```sql
-- dividend_amount 컬럼 추가 (기존 테이블 마이그레이션용)
alter table trades add column if not exists dividend_amount float;
```

> **주의**: Supabase를 이미 사용 중이라면 SQL Editor에서 ALTER 문만 따로 실행하면 됩니다.

---

## 🔴 수정 2 — `db.py` get_past_context 보안 강화

### 문제

현재 `fix_instructions.md`(이전 지시서)에서 제안한 수정안:

```python
if user_id:
    query = query.eq("user_id", user_id)
response = query.execute()
```

이 패턴은 `user_id`가 빈 문자열(`""`)이면 `if user_id:` 분기가 실행되지 않아
**user_id 필터 없이 전체 사용자 데이터를 조회**합니다.

### 수정

**파일**: `stock-diary/db.py`
**함수**: `get_past_context`

**현재 코드 (시그니처 포함):**
```python
def get_past_context(tags, supabase, user_id: str = ""):
    if not tags:
        return ""
    ...
    try:
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

**수정 후:**
```python
def get_past_context(tags, supabase, user_id: str = ""):
    if not user_id:          # user_id 없으면 즉시 종료 (빈 문자열 포함)
        return ""
    if not tags:
        return ""
    ...
    try:
        response = (
            supabase.table("journals")
            .select("created_at, content")
            .eq("user_id", user_id)      # 항상 실행 (조건부 아님)
            .like("tags", f"%{core_tag}%")
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
```

---

## 🔴 수정 3 — `db.py` calculate_scores 함수 시그니처 불일치 (크래시)

### 문제

> ⚠️ 이 버그는 외부 보고서에 없는 항목으로, 코드 직접 검증 중 발견했습니다.

새로운 `tab_diary.py`(리팩토링 후)에서 `calculate_scores`를 이렇게 호출합니다:

```python
# tab_diary.py 136번째 줄
current_scores = calculate_scores(supabase, st.session_state.get("user_id", ""))
```

그런데 `db.py`의 `calculate_scores` 함수는 인자를 하나만 받습니다:

```python
def calculate_scores(supabase):   # ← user_id 인자 없음
```

→ 앱 실행 시 `TypeError: calculate_scores() takes 1 positional argument but 2 were given` 크래시.

### 수정

**파일**: `stock-diary/db.py`
**함수**: `calculate_scores`

**현재 코드:**
```python
def calculate_scores(supabase):
    """최근 30일 일기를 기반으로 투자 능력치 점수를 계산."""
    thirty_days_ago = (
        datetime.datetime.now(timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()

    try:
        response = (
            supabase.table("journals")
            .select("created_at, tags")
            .gte("created_at", thirty_days_ago)
            .order("created_at", desc=True)
            .execute()
        )
```

**수정 후:**
```python
def calculate_scores(supabase, user_id: str = ""):
    """최근 30일 일기를 기반으로 투자 능력치 점수를 계산."""
    if not user_id:
        return {"원칙 준수": 0, "멘탈 방어": 0, "성실도": 0, "자기 객관화": 0}

    thirty_days_ago = (
        datetime.datetime.now(timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()

    try:
        response = (
            supabase.table("journals")
            .select("created_at, tags")
            .eq("user_id", user_id)      # user_id 필터 추가
            .gte("created_at", thirty_days_ago)
            .order("created_at", desc=True)
            .execute()
        )
```

`__all__`에 `calculate_scores`가 이미 있으면 export는 유지.

---

## 🔴 수정 4 — UX 차단: diff 없을 때 이미지 업로드 후 진행 불가

### 문제

`diary_upload.py`(리팩토링 후 파일, 구 `tab_diary.py`의 verify_data 단계)에서
`diff_data`가 비어있으면 저장 버튼이 `disabled=True`로 막힙니다.

```python
submit_btn = st.form_submit_button(
    "💾 확정 및 장바구니 담기",
    type="primary",
    disabled=not diff_data      # ← diff_data 없으면 버튼 비활성
)
```

사용자가 이미지를 올렸는데 현재 DB 잔고와 변동이 없으면(예: 동일 잔고 캡처)
저장·취소 외에 선택지가 없어 감정 일기만 남기려는 경우 완전히 막힙니다.

### 수정

**파일**: `stock-diary/diary_upload.py`
**위치**: `diff_data`가 비어있을 때 표시되는 성공 메시지 바로 아래

**현재 코드:**
```python
if not diff_data:
    st.success("🎉 DB 잔고와 동일합니다. 새로 변동된 내역이 없습니다.")
```

**수정 후:**
```python
if not diff_data:
    st.success("🎉 DB 잔고와 동일합니다. 새로 변동된 내역이 없습니다.")
    if st.button("📝 매매 없이 감정 일기만 저장하기", key="diary_only_btn"):
        st.session_state['current_step'] = 'final_analysis'
        st.rerun()
```

---

## 🟠 수정 5 — AI 추출 가격이 0일 때 평단가 왜곡

### 문제

`diary_upload.py`(구 `tab_diary.py` 최종 분석 단계)에서
종목 티커를 찾지 못하거나 시간외 거래로 가격 조회 실패 시 `real_price = 0.0`으로 저장됩니다.

```python
real_price = bulk_trade_prices.get(ticker) or 0.0   # 가격 없으면 0
```

이후 `get_real_inventory`에서 평단가 계산:
```python
inventory_map[name]["총매수금액"] += (qty * price)   # price=0이면 금액도 0
# ...
avg_price = 총매수금액 / 총매수수량   # 평단가가 실제보다 낮아짐
```

→ 평단가가 0으로 희석되어 수익률이 실제보다 훨씬 높게 표시됩니다.

### 수정

**파일**: `stock-diary/diary_upload.py`
**위치**: `trades_to_insert` 목록을 조립하는 for 루프 내부

**현재 코드:**
```python
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
        ...
    })
```

**수정 후:**
```python
for trade in extracted_trades:
    ticker = trade["_ticker"]
    if ticker:
        real_price = bulk_trade_prices.get(ticker) or 0.0
        currency   = "KRW" if ticker.endswith(".KS") else "USD"
    else:
        real_price = 0.0
        currency   = "KRW"

    # 가격이 0이면 평단가 왜곡 방지를 위해 저장 제외하고 사용자에게 안내
    if real_price <= 0:
        st.warning(
            f"⚠️ **{trade['_normalized_name']}** 현재가를 불러오지 못해 평단가 기록을 건너뜁니다. "
            f"나중에 '과거 기록 조회'에서 직접 수정해 주세요."
        )
        continue

    trades_to_insert.append({
        "stock_name": trade["_normalized_name"],
        "quantity":   abs(trade["quantity"]),
        "price":      real_price,
        ...
    })
```

---

## 🟠 수정 6 — Gemini 모델명 확인 필요

### 문제

`diary_chat.py` 및 `diary_upload.py`(리팩토링 후 파일들)에서 사용 중인 모델명:

```python
MODEL_NAME = "gemini-3.1-flash-lite-preview"
```

2025년 5월 기준 Google Gemini API에 `gemini-3.1` 계열 모델은 존재하지 않습니다.
→ API 호출 시 `404 NotFound` 오류 발생 가능.

### 수정

`diary_chat.py`, `diary_upload.py`의 `MODEL_NAME` 상수를 아래 중 하나로 변경:

```python
# 권장: 안정 버전
MODEL_NAME = "gemini-2.0-flash-lite"

# 또는 최신 프리뷰 (변경될 수 있음)
MODEL_NAME = "gemini-2.0-flash-lite-preview-02-05"
```

> 정확한 모델 목록은 [Google AI Studio](https://aistudio.google.com) 또는
> `client.models.list()` 호출로 확인하세요.

---

## 수정 우선순위 요약

| 순위 | 항목 | 파일 | 증상 |
|---|---|---|---|
| 🔴 1 | `dividend_amount` 컬럼 추가 | `supabase_schema.sql` | 배당금 저장 즉시 크래시 |
| 🔴 2 | `calculate_scores` 시그니처 수정 | `db.py` | 능력치 차트 크래시 |
| 🔴 3 | `get_past_context` user_id 빈값 처리 강화 | `db.py` | 데이터 보안 위험 |
| 🔴 4 | diff 없을 때 감정 일기만 저장 버튼 추가 | `diary_upload.py` | UX 완전 차단 |
| 🟠 5 | 가격 0 저장 건너뛰기 | `diary_upload.py` | 평단가 왜곡 |
| 🟠 6 | Gemini 모델명 수정 | `diary_chat.py`, `diary_upload.py` | AI 기능 전체 불작동 |
