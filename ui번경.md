# 모바일 UI 최적화 변경 내역

## ✅ 적용 완료된 CSS (app.py → toss_style 변수)

### 1. 전역 공통 설정 (모든 화면)
- **Pretendard 폰트** 적용 (CDN)
- **word-break: keep-all** — 한국어 단어 중간 줄바꿈 방지
- **header-anchor 숨김** — 제목 옆 자동 링크 아이콘 제거
- **본문 폰트** 14px, 줄간격 1.6 고정
- **배경색** #F9FAFB (연한 회색), **텍스트** #191F28 (소프트 블랙)
- **버튼 최소 높이** 44px (모바일 터치 영역 확보)
- **iOS Safe Area** 패딩 적용 (env(safe-area-inset-*))
- **block-container 최대 폭** 600px (모바일 앱 느낌)

### 2. 모바일 전용 스타일 (@media max-width: 600px)

```css
/* 메인 타이틀 (h1) — 📈 AI 주식 페이스메이커 등 */
.stMarkdown h1, h1 {
    font-size: 1.5rem !important;       /* 기존 1.8rem → 축소 */
    letter-spacing: -0.5px !important;  /* 자간 좁혀 한 줄 유도 */
    word-break: keep-all !important;    /* 단어 단위 줄바꿈 강제 */
    line-height: 1.3 !important;
}

/* 서브 타이틀 (h2) */
.stMarkdown h2, h2 {
    font-size: 1.25rem !important;
    letter-spacing: -0.3px !important;
    word-break: keep-all !important;
}

/* 소제목 (h3) — 📦 나의 보물함 등 */
.stMarkdown h3, h3 {
    font-size: 1.1rem !important;
    word-break: keep-all !important;
}

/* 본문 패딩 축소 */
.block-container {
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* 탭 버튼 텍스트 축소 */
div[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-size: 0.85rem !important;
    padding: 10px 4px !important;
}

/* 파일 업로더 라벨 축소 */
[data-testid="stFileUploader"] label {
    font-size: 0.9rem !important;
}
```

---

## 💡 수정 포인트 요약

| 항목 | 변경 전 | 변경 후 | 이유 |
|------|---------|---------|------|
| h1 폰트 크기 (모바일) | 1.8rem | 1.5rem | 칸내림 방지 |
| h1 letter-spacing | 없음 | -0.5px | 자간 좁혀 한 줄 유도 |
| h1 line-height | 없음 | 1.3 | 줄간격 최적화 |
| h2 모바일 스타일 | 없음 | 1.25rem | 계층 구조 유지 |
| h3 모바일 스타일 | 없음 | 1.1rem | 계층 구조 유지 |
| 탭 버튼 | 없음 | 0.85rem, 패딩 조정 | 4개 탭 한 줄에 표시 |
| 파일 업로더 | 없음 | 0.9rem | 모바일 레이아웃 개선 |

---

## 📌 핵심 CSS 속성 설명

- **@media (max-width: 600px)**: PC 화면 원래 크기 유지, 스마트폰 화면에서만 적용
- **font-size 축소 + letter-spacing**: 폰트 크기를 줄이며 자간도 미세하게 좁혀 제한된 모바일 폭에 텍스트가 들어가도록 유도
- **word-break: keep-all**: "페이스메이커" 같은 단어가 "페이스메이 / 커" 처럼 쪼개지지 않도록 강제
- **line-height: 1.3**: 제목 줄간격 최적화로 여백 낭비 방지
