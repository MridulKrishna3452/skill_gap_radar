import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from app.database.connection import db_manager
from app.analytics.gap_analysis import GapAnalysisEngine

dash.register_page(__name__, path="/", title="Radar Home - Skill Gap Radar AI")

def layout():
    # 1. Fetch current statistics from the DB
    df_jobs = db_manager.get_jobs_df()
    df_curr = db_manager.get_curriculum_df()
    
    # Calculate stats using the Gap Analysis Engine
    gap_engine = GapAnalysisEngine()
    analysis = gap_engine.compute_gap_analysis()
    
    total_jobs = len(df_jobs)
    total_curriculum_topics = len(df_curr)
    coverage_pct = analysis.get("coverage_pct", 0.0)
    gap_score = analysis.get("gap_score", 100.0)

    # 2. Build radar chart comparing demand across disciplines
    # Let's mock a nice comparison for the roles
    role_data = {
        "Role": ["Data Engineer", "AI Engineer", "DevOps Engineer", "Cloud Engineer", "Software Engineer"],
        "Industry Demand": [90, 95, 80, 85, 75],
        "Curriculum Coverage": [40, 50, 20, 10, 60]
    }
    df_roles = pd.DataFrame(role_data)
    
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=df_roles["Industry Demand"],
        theta=df_roles["Role"],
        fill='toself',
        name='Industry Demand',
        line_color='#06b6d4'
    ))
    fig_radar.add_trace(go.Scatterpolar(
        r=df_roles["Curriculum Coverage"],
        theta=df_roles["Role"],
        fill='toself',
        name='Curriculum Coverage',
        line_color='#8b5cf6'
    ))
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100]),
            gridshape='circular',
            bgcolor='rgba(0,0,0,0)'
        ),
        showlegend=True,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', family='Outfit'),
        margin=dict(t=30, b=30, l=40, r=40)
    )

    # KPI Layout
    kpis = dbc.Row(
        [
            dbc.Col(
                html.Div(
                    [
                        html.P("Total Jobs Scraped", className="text-secondary text-uppercase fw-bold small mb-1"),
                        html.Div(f"{total_jobs}", className="kpi-value kpi-teal"),
                        html.Span("Active industry sources", className="text-muted small")
                    ],
                    className="glass-card"
                ),
                width=12, md=3, className="mb-4"
            ),
            dbc.Col(
                html.Div(
                    [
                        html.P("Syllabus Coverage %", className="text-secondary text-uppercase fw-bold small mb-1"),
                        html.Div(f"{coverage_pct}%", className="kpi-value kpi-violet"),
                        html.Span("Target skills taught", className="text-muted small")
                    ],
                    className="glass-card"
                ),
                width=12, md=3, className="mb-4"
            ),
            dbc.Col(
                html.Div(
                    [
                        html.P("Overall Gap Score", className="text-secondary text-uppercase fw-bold small mb-1"),
                        html.Div(f"{gap_score}", className="kpi-value kpi-pink"),
                        html.Span("Lower is better", className="text-muted small")
                    ],
                    className="glass-card"
                ),
                width=12, md=3, className="mb-4"
            ),
            dbc.Col(
                html.Div(
                    [
                        html.P("Curriculum Modules", className="text-secondary text-uppercase fw-bold small mb-1"),
                        html.Div(f"{total_curriculum_topics}", className="kpi-value"),
                        html.Span("Subjects & topics parsed", className="text-muted small")
                    ],
                    className="glass-card"
                ),
                width=12, md=3, className="mb-4"
            )
        ]
    )

    return html.Div(
        [
            html.Div(
                [
                    html.H1("Skill Gap Radar AI", className="gradient-text fw-bold mb-1"),
                    html.P("Industry Demand vs University Syllabus Analytics Platform", className="text-muted fs-5"),
                ],
                className="mb-5"
            ),
            
            kpis,
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Role-Based Skills Gap Radar", className="text-white mb-4 fw-semibold"),
                                dcc.Graph(figure=fig_radar, config={"displayModeBar": False})
                            ],
                            className="glass-card h-100"
                        ),
                        width=12, lg=7, className="mb-4"
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Platform Capabilities", className="text-white mb-4 fw-semibold"),
                                html.Ul(
                                    [
                                        html.Li(
                                            [
                                                html.Strong("Aggregated Scrapers: ", className="text-cyan"),
                                                "Continuous ingestion of job openings from Naukri, Internshala, and custom CSV/JSON loaders."
                                            ],
                                            className="text-muted mb-3"
                                        ),
                                        html.Li(
                                            [
                                                html.Strong("NLP Skill Extraction: ", className="text-cyan"),
                                                "Utilizing Spacy phrase matchers to extract key technical skills directly from descriptions."
                                            ],
                                            className="text-muted mb-3"
                                        ),
                                        html.Li(
                                            [
                                                html.Strong("Syllabus Parsing: ", className="text-cyan"),
                                                "Extraction of subjects, units, and learning outcomes from university syllabus PDFs."
                                            ],
                                            className="text-muted mb-3"
                                        ),
                                        html.Li(
                                            [
                                                html.Strong("AI-Driven Roadmaps: ", className="text-cyan"),
                                                "Targeted learning roadmaps recommending specific topics, time estimates, and materials for missing skills."
                                            ],
                                            className="text-muted mb-3"
                                        )
                                    ],
                                    className="list-unstyled ps-0"
                                )
                            ],
                            className="glass-card h-100"
                        ),
                        width=12, lg=5, className="mb-4"
                    )
                ]
            )
        ]
    )
