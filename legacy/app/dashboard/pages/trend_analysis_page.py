import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from app.analytics.trend_analysis import TrendAnalysisEngine

dash.register_page(__name__, path="/trend-analysis", title="Trend Analysis - Skill Gap Radar AI")

def layout():
    engine = TrendAnalysisEngine()
    summary = engine.get_trends_summary()
    
    df_trends = summary.get("all_trends", pd.DataFrame())
    
    if df_trends.empty:
        return html.Div([html.H3("No trend history available. Load more historical job data first.", className="text-danger")])

    # Time series line chart of top 5 skills
    # Filter trends for the top 5 overall most frequent skills
    top_skills = df_trends.groupby("skill_name")["frequency"].sum().nlargest(5).index
    df_top_trends = df_trends[df_trends["skill_name"].isin(top_skills)]
    
    # Sort by period for proper chronological line rendering
    df_top_trends = df_top_trends.sort_values(by="period")
    
    fig_line = px.line(
        df_top_trends,
        x="period",
        y="frequency",
        color="skill_name",
        markers=True,
        title="Monthly Demand Trends for Top 5 Core Skills",
        labels={"period": "Month", "frequency": "Job Mentions", "skill_name": "Technology"}
    )
    
    fig_line.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', family='Outfit'),
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        margin=dict(t=50, b=20, l=40, r=20)
    )

    # Render list helper
    def render_trend_cards(title: str, items: list, color_class: str, is_pct: bool = True):
        card_items = []
        if not items:
            card_items.append(html.Div("No trends found.", className="text-muted py-2"))
        else:
            for item in items:
                val = f"{round(item['growth_rate'] * 100, 1)}%" if is_pct else f"Freq: {item['frequency']}"
                card_items.append(
                    html.Div(
                        [
                            html.Span(item["skill_name"], className="fw-semibold text-white"),
                            html.Span(val, className=f"badge {color_class} px-3 py-2 rounded-3")
                        ],
                        className="d-flex justify-content-between align-items-center py-3 border-bottom border-secondary"
                    )
                )
        return html.Div(
            [
                html.H5(title, className="text-white fw-bold mb-3 pb-2 border-bottom border-secondary"),
                html.Div(card_items)
            ],
            className="glass-card h-100"
        )

    growing_card = render_trend_cards("Top Growing Skills", summary.get("growing", []), "bg-success text-white")
    declining_card = render_trend_cards("Top Declining Skills", summary.get("declining", []), "bg-danger text-white")
    emerging_card = render_trend_cards("Emerging Technologies", summary.get("emerging", []), "bg-info text-dark", is_pct=False)

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Market Trend Analysis", className="gradient-text fw-bold mb-1"),
                    html.P("Tracking month-over-month shifts in technical requirements and emerging frameworks.", className="text-muted"),
                ],
                className="mb-5"
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                dcc.Graph(figure=fig_line, config={"displayModeBar": False})
                            ],
                            className="glass-card mb-4"
                        ),
                        width=12
                    )
                ]
            ),
            
            dbc.Row(
                [
                    dbc.Col(growing_card, width=12, lg=4, className="mb-4"),
                    dbc.Col(declining_card, width=12, lg=4, className="mb-4"),
                    dbc.Col(emerging_card, width=12, lg=4, className="mb-4")
                ]
            )
        ]
    )
