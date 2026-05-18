import plotly.graph_objects as go
import streamlit as st
import bleach


# AI 생성 HTML에서 허용할 태그/속성 화이트리스트 (XSS 방어)
_ALLOWED_TAGS = [
    "b", "i", "u", "em", "strong", "br", "p", "span", "div",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
]
_ALLOWED_ATTRIBUTES = {
    "span": ["style"],
    "div": ["style"],
    "p": ["style"],
}


def sanitize_html(html_str: str) -> str:
    """AI 생성 HTML을 화이트리스트 기반으로 정화하여 XSS를 방어합니다."""
    if not html_str:
        return ""
    return bleach.clean(
        html_str,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )

def render_radar_chart(scores: dict):
    categories = list(scores.keys())
    values = list(scores.values())
    categories.append(categories[0])
    values.append(values[0])

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        line=dict(color='#3182F6', width=2),
        fillcolor='rgba(49, 130, 246, 0.25)'
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True, 
                range=[0, 100], 
                color='#8B95A1',
                gridcolor='rgba(229, 232, 235, 0.6)',
                linecolor='rgba(229, 232, 235, 0.6)'
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color='#4E5968', family='Pretendard'),
                gridcolor='rgba(229, 232, 235, 0.6)'
            ),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=45, r=45, t=30, b=30),
        showlegend=False,
        height=280
    )
    return fig

# pyrefly: ignore [bad-function-definition]
def card(title: str, content_html: str, icon: str = None):
    icon_html = f"<span style='font-size: 1.25em; margin-right: 6px;'>{icon}</span>" if icon else ""
    title_html = f"<div style='font-weight: 700; font-size: 1.05em; color: #191F28; margin-bottom: 10px; display: flex; align-items: center;'>{icon_html}{title}</div>" if title else ""
    card_html = f"""
    <div style="
        background: #FFFFFF;
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #E5E8EB;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.02);
        margin-bottom: 16px;
    ">
        {title_html}
        <div style="color: #4E5968; font-size: 0.95em; line-height: 1.6; font-family: Pretendard;">
            {content_html}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

def banner(message: str, type: str = "info"):
    colors = {
        "info": ("#E8F4FF", "#3182F6"),
        "success": ("#EBFBEE", "#2B8A3E"),
        "warning": ("#FFF9DB", "#F59F00"),
        "error": ("#FFE3E3", "#E03131"),
    }
    bg, text = colors.get(type, colors["info"])
    banner_html = f"""
    <div style="
        background-color: {bg};
        color: {text};
        border-radius: 12px;
        padding: 14px 18px;
        font-size: 0.92em;
        font-weight: 500;
        margin-bottom: 16px;
        border: 1px solid {text}25;
        font-family: Pretendard;
        line-height: 1.5;
    ">
        {message}
    </div>
    """
    st.markdown(banner_html, unsafe_allow_html=True)
