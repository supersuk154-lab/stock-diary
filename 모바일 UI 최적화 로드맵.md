📱 AI 주식 페이스메이커 모바일 UI 최적화 로드맵
1. 🔗 거슬리는 '제목 링크(Anchor)' 아이콘 숨기기
문제 원인: Streamlit은 st.title, st.subheader 또는 마크다운 헤딩(#)을 사용할 때, 제목 옆에 자동으로 하이퍼링크 아이콘을 생성합니다. 모바일에서는 불필요하고 지저분해 보입니다.
수정 요청 가이드:

app.py의 toss_style 변수(CSS 정의 부분)에 Streamlit 헤더 앵커 링크를 숨기는 속성을 추가해 달라고 요청하세요.

적용할 CSS 논리:

CSS
/* 제목 옆 자동 생성되는 링크 아이콘 숨기기 */
.stMarkdown a.header-anchor {
    display: none !important;
}
2. 🔠 한국어 어절 끊김(줄바꿈) 현상 해결
문제 원인: "오늘의 상태 (터치해서 선 / 택)", "AI 주식 페이스 / 메이커" 처럼 단어 중간에서 텍스트가 밑으로 떨어지는 것은 CSS의 단어 분리 규칙 때문입니다.
수정 요청 가이드:

app.py의 toss_style에 한국어 줄바꿈 최적화 속성을 추가해 달라고 요청하세요.

적용할 CSS 논리:

CSS
/* 단어 중간에서 줄바꿈 방지 (한국어 최적화) */
html, body, [class*="css"], .stMarkdown p, h1, h2, h3, h4, h5, h6 {
    word-break: keep-all !important;
    overflow-wrap: break-word !important;
}
3. 📦 '나의 보물함' 긴 종목명 UI 깨짐 방지
문제 원인: "KODEX 삼성전자SK하이닉스채권혼합" 같은 긴 ETF 이름이 들어가면, 우측의 가격/수익률 텍스트를 밀어내거나 텍스트가 겹치는 현상이 발생합니다.
수정 요청 가이드:

diary_inventory.py 내의 render_inventory_section 함수에서 종목 리스트를 렌더링하는 HTML 구조를 수정해 달라고 요청하세요.

적용할 레이아웃 논리:

왼쪽 영역(종목명)과 오른쪽 영역(가격)을 나누는 Flexbox에서, 왼쪽 종목명 텍스트에 text-overflow: ellipsis; 와 white-space: nowrap;, overflow: hidden; 을 적용하여 긴 이름은 "KODEX 삼성전자..." 처럼 말줄임표 처리되도록 변경해야 합니다.

오른쪽 가격 영역은 flex-shrink: 0;으로 설정하여 공간을 무조건 확보하도록 합니다.

4. 📐 모바일 타이포그래피(글씨 크기) 다듬기
문제 원인: 데스크톱 기준의 폰트 사이즈가 모바일 기기에 그대로 적용되어 화면이 답답해 보입니다 (특히 메인 타이틀).
수정 요청 가이드:

app.py의 모바일 뷰어용 미디어 쿼리(@media (max-width: 600px))를 추가해 달라고 요청하세요.

적용할 CSS 논리:

h1 태그(메인 타이틀)의 폰트 사이즈를 모바일에서는 조금 더 작게(예: 1.8rem) 줄이도록 설정합니다.

좌우 패딩을 현재보다 약간만 더 줄여서(예: 1rem) 좁은 모바일 화면을 더 넓게 쓰도록 다듬어 달라고 하세요.