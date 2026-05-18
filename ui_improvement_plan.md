# UI/UX & 코드 구조 개선 계획

## 📊 전체 코드·UI 현황 분석 (요약)

| 영역 | 현재 상태 | 문제·리스크 |
|------|-----------|--------------|
| **프로젝트 구조** | `app.py` → 메인 라우팅, 3개의 탭 모듈(`tab_diary`, `tab_records`, `tab_settings`) | 파일 간 의존성(`supabase`, `ai_client`)를 인수로 전달하고 있지 않은 곳 존재 → 런타임 `ImportError/TypeError` 발생 |
| **데이터 레이어** | `db.py`에 DB · 점수·캐시 로직 집중 | `has_tag`·`get_recent_journals`가 누락·중복, 함수 시그니처가 일관되지 않음 |
| **UI 구성** | Streamlit 기본 위젯·Markdown 사용, 색상·폰트가 “기본” 수준 | <ul><li>다크/라이트 테마 전환 없음</li><li>색상·버튼 스타일이 통일되지 않음</li><li>섹션 간 마진·패딩이 불규칙</li><li>시각적 강조(차트·아이콘·그라디언트) 부족</li></ul> |
| **사용자 흐름** | <ul><li>‘동굴 모드’(Zen) 토글 → UI 전체 숨김</li><li>이미지 업로드 → AI 분석</li><li>태그 선택 → 챗봇 대화</li></ul> | UI가 한 페이지에 과다하게 쌓여 가독성 저하, 모바일·소형 화면에서 스크롤이 길어짐 |
| **코드 품질** | 함수·변수 명명은 대부분 명확<br>하지만 <ul><li>중복 `supabase` 파라미터 전달</li><li>전역 `st.session_state` 사용이 과도</li><li>에러 핸들링이 간소화돼 있음</li></ul> | 유지보수·테스트가 어려움 |
| **성능** | `st.cache_data` 사용은 적절하지만 **cache key**에 `supabase` 객체가 포함되지 않아 매 호출마다 새로 조회될 가능성 존재 | 불필요한 API 호출·응답 지연 |

---

## 🎨 UI·UX 디자인 개선 방안

| 개선 항목 | 구체적 내용 | 기대 효과 |
|-----------|-------------|-----------|
| **전체 테마** | - Streamlit `config.toml`에 다크·라이트 테마 정의 <br>- 사용자에게 `st.toggle("다크 모드")` 로 실시간 전환 제공 | 눈 피로 감소, 현대적 감각 |
| **색상·타이포그래피** | - **프라이머리 색**: `#3182F6` (블루) + 보조 `#F04452` (레드) <br>- Google Font `Inter` 로 전체 적용 (`st.markdown("<style>...</style>", unsafe_allow_html=True)`) | 깔끔하고 일관된 브랜드 이미지 |
| **카드·컨테이너** | - 모든 섹션을 **Glassmorphism** 스타일 `<div>`(반투명 배경 + 블러) 로 감싸고 `border-radius:12px` | 시각적 구분·입체감 강화 |
| **마이크로 애니메이션** | - `st.progress` → `st.experimental_rerun` 대신 **Plotly** `animation_frame` 사용 <br>- 버튼 hover 효과 (CSS) | 인터랙션 감각 향상 |
| **차트 스타일** | - Radar 차트 색상·라인 두께 커스텀 <br>- `plotly` `layout`에 `paper_bgcolor: "rgba(0,0,0,0)"` 적용 | 차트가 UI와 자연스럽게 어울림 |
| **레이아웃 재구성** | - **2‑column** 레이아웃: 왼쪽에 이미지·업로드, 오른쪽에 결과·피드백 <br>- 태그 선택을 **st.pills** 대신 **st.checkbox** 그룹화해서 가로 한 줄에 표시 | 모바일·데스크탑 모두 가독성 높음 |
| **요약·알림 배너** | - `st.success/info/warning` 대신 **custom banner** (`<div class="banner">…</div>`) 로 스타일 통일 | UI 통일감 확보 |
| **접근성** | - 모든 버튼·입력에 `aria-label`(HTML) 추가 <br>- 색 대비 ≥ 4.5:1 보장 | 접근성·시각장애인 사용 가능 |
| **코드‑UI 분리** | - UI 컴포넌트를 `ui_components.py`에 몰아두고 **재사용 함수**(`card()`, `banner()`) 제공 | 중복 UI 코드 제거, 유지보수 용이 |

---

## 🛠️ 구현 로드맵 (초안)

### 1️⃣ 설계·공통 설정
- **`config.toml`**에 다크/라이트 테마와 기본 색상·폰트 정의  
  ```toml
  [theme]
  primaryColor = "#3182F6"
  backgroundColor = "#F8F9FA"
  secondaryBackgroundColor = "#FFFFFF"
  textColor = "#212529"
  font = "Inter"
  ```
- **`ui_components.py`**에 `card(content, title=None, icon=None)`, `banner(message, type="info")`, `gradient_div(...)` 등 재사용 함수 구현.

### 2️⃣ UI 재작성 (각 탭)
| 탭 | 주요 변경 |
|---|-----------|
| **Diary (`tab_diary.py`)** | - 이미지 업로드·가림막을 **좌우 2‑col** 레이아웃<br>- `zen_mode` 토글 → `st.sidebar`에 배치, 카드형 UI 숨김<br>- 점수·Radar 차트를 `card()` 안에 삽입, 다크 모드에서도 가시성 확보 |
| **Records (`tab_records.py`)** | - 과거 일기 리스트를 **스크롤 가능한 카드** 형태로 전환<br>- `st.table` → `st.dataframe` + `plotly` 히스토리 차트 (월별 투자 성과) |
| **Settings (`tab_settings.py`)** | - 비밀번호·백업 UI를 **폼 카드** 로 감싸고, 배경에 미세 그라디언트 적용 |
| **공통** | - 모든 `st.button`에 CSS hover 효과 (`.stButton > button:hover {background:#e2e8f0;}`)<br>- `st.markdown("---")` 대신 `ui_components.banner("---")` 등 맞춤 구분선 |

### 3️⃣ Supabase·함수 시그니처 정리
- 모든 DB·AI 함수에 **`supabase`** 인수 명시 (이미 다수 수정).  
- `db.py`에 **`has_tag`**, **`get_recent_journals`** 등 누락된 헬퍼를 한 번에 정리하여 `__all__`에 추가.  
- 캐시 키에 `user_id`·`supabase`를 포함하도록 `@st.cache_data` 데코레이터 수정.

### 4️⃣ 스타일·CSS 적용
- `st.markdown("<style> … </style>", unsafe_allow_html=True)` 로 전역 CSS 삽입 (버튼, 카드, 배경 블러).  
- 다크 모드 토글 시 `st.experimental_set_query_params(dark="1")` 로 상태 유지.

### 5️⃣ 테스트·배포
- **유닛 테스트** (`pytest`) 로 `calculate_scores(supabase)`, `get_dividend_work_stats(..., supabase)` 등 핵심 함수 검증.  
- 로컬 `streamlit run app.py` 로 UI 흐름 검증 → **Streamlit Cloud** 배포 전 **성능 프로파일링** (네트워크 호출 최소화).

---

## 📌 다음 단계 – 사용자 승인 요청
1️⃣ **UI 스타일 시안**(CSS + 컴포넌트 정의) – 코드 스니펫을 제공하고, 색상·폰트·카드 레이아웃에 대한 피드백을 받습니다。
2️⃣ **구조/함수 정리 계획** – Supabase 파라미터 일관화, 캐시 키 보강, `has_tag`·`get_recent_journals` 추가를 포함합니다。
3️⃣ **구현 일정** – 1 일(디자인·컴포넌트 구현) + 1 일(기능·테스트) 예상。

> **요청**: 위 로드맵과 UI·코드 개선 제안을 검토하시고, 어느 항목을 먼저 진행할지, 색상·폰트 등 선호하는 디자인 옵션(예: 다크 모드 기본 ON/OFF) 알려주시면 **승인** 후 실제 코드를 적용합니다。

*승인 또는 추가 의견을 주시면 바로 작업에 들어가겠습니다.*
