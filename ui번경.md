제목 폰트 크기 및 칸내림 해결 요청 프롬프트
"현재 Streamlit 앱의 모바일 UI에서 제목 글씨가 너무 커서 어색하게 칸내림(줄바꿈)이 발생하고 있어. app.py의 toss_style 변수(CSS 정의 부분)에 아래의 모바일 전용 폰트 최적화 코드를 추가해서 코드를 업데이트해 줘."

[추가할 CSS 코드]

CSS
/* 모바일 환경(화면 폭 600px 이하) 제목 폰트 크기 및 줄바꿈 최적화 */
@media (max-width: 600px) {
    /* 메인 타이틀 (h1) - 📉 AI 주식 페이스메이커 등 */
    .stMarkdown h1, h1 {
        font-size: 1.5rem !important; /* 기존보다 작게 설정 */
        letter-spacing: -0.5px !important; /* 자간을 살짝 좁혀서 한 줄에 들어가게 유도 */
        word-break: keep-all !important; /* 단어 단위로 끊어지도록 강제 */
        line-height: 1.3 !important;
    }
    
    /* 서브 타이틀 (h2) */
    .stMarkdown h2, h2 {
        font-size: 1.25rem !important;
        letter-spacing: -0.3px !important;
        word-break: keep-all !important;
    }
    
    /* 소제목 (h3) - 📦 나의 보물함 (실시간) 등 */
    .stMarkdown h3, h3 {
        font-size: 1.1rem !important;
        word-break: keep-all !important;
    }
    
    /* 제목 옆의 불필요한 링크 아이콘 숨기기 */
    .stMarkdown a.header-anchor {
        display: none !important;
    }
}
💡 수정 포인트 요약
@media (max-width: 600px): PC 화면에서는 원래 크기를 유지하고, 스마트폰 화면(폭 600px 이하)에서만 글씨 크기를 줄이도록 안전장치를 걸었습니다.

font-size 축소 & letter-spacing 조정: 폰트 크기를 줄이면서 글자 사이의 간격(자간)도 미세하게 좁혀서, 제한된 모바일 화면 폭 안에 텍스트가 쏙 들어가도록 유도했습니다.

word-break: keep-all: "페이스메이커" 같은 단어가 "페이스메이 / 커" 처럼 쪼개지지 않도록 강제하는 속성입니다.

이렇게 적용하시면 제목들이 훨씬 슬림해지면서 세련된 앱 화면을 보실 수 있을 겁니다! 또 눈에 거슬리는 디자인 요소가 있다면 언제든 편하게 말씀해 주세요.