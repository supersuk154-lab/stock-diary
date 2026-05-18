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