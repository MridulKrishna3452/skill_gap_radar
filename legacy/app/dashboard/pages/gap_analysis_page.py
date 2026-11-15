import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from app.database.connection import db_manager
from app.analytics.gap_analysis import GapAnalysisEngine

dash.register_page(__name__, path="/gap-analysis", title="Gap Analysis - Skill Gap Radar AI")

def layout():
    gap_engine = GapAnalysisEngine()
    analysis = gap_engine.compute_gap_analysis()
    
    df_comp = analysis.get("skills_comparison", pd.DataFrame())
    
    if df_comp.empty:
        return html.Div([html.H3("No gap data available. Ingest job and curriculum data first.", className="text-danger")])

    # Let's take top 10 skills for Sankey to look extremely clean and elegant
    top_n = df_comp.head(10)
    
    # Nodes list
    # Node 0: Job Market (Industry Source)
    # Nodes 1..10: Skills
    # Node 11: Covered in Syllabus
    # Node 12: Missing in Syllabus
    nodes = ["Job Market"] + list(top_n["skill"]) + ["Taught in Syllabus", "Missing in Syllabus"]
    
    # Build links
    sources = []
    targets = []
    values = []
    colors = []
    
    # Link 1: Job Market -> Skill (using industry frequency)
    for i, row in enumerate(top_n.itertuples(), start=1):
        sources.append(0)
        targets.append(i)
        values.append(int(row.industry_frequency))
        colors.append("rgba(6, 182, 212, 0.2)") # teal-ish
        
        # Link 2: Skill -> Covered (node 11) or Missing (node 12)
        sources.append(i)
        if row.is_covered:
            targets.append(11) # Taught
            colors.append("rgba(16, 185, 129, 0.4)") # green
        else:
            targets.append(12) # Missing
            colors.append("rgba(239, 68, 68, 0.4)") # red
        values.append(int(row.industry_frequency))

    fig_sankey = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=nodes,
            color=["#3b82f6"] + ["#06b6d4"]*10 + ["#10b981", "#ef4444"]
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=colors
        )
    )])
    
    fig_sankey.update_layout(
        title_text="Industry Skills Ingestion to Curriculum Mapping (Top 10 Skills)",
        font=dict(color='#94a3b8', family='Outfit', size=11),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=50, b=20, l=20, r=20)
    )

    # Build comparison table rows
    table_rows = []
    for row in df_comp.itertuples():
        badge = html.Span("Covered", className="badge-covered") if row.is_covered else html.Span("Missing", className="badge-missing")
        table_rows.append(
            html.Tr([
                html.Td(row.skill, className="fw-semibold text-white"),
                html.Td(f"{row.demand_pct}%"),
                html.Td(badge),
                html.Td(row.gap_score, className="text-pink fw-bold")
            ])
        )

    table_comp = html.Table(
        [
            html.Thead(
                html.Tr([
                    html.Th("Skill"),
                    html.Th("Industry Demand %"),
                    html.Th("Academic Status"),
                    html.Th("Skill Gap Score")
                ])
            ),
            html.Tbody(table_rows)
        ],
        className="custom-table"
    )

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Gap Analysis Engine", className="gradient-text fw-bold mb-1"),
                    html.P("Comparing industrial skill demand percentages against university coverage.", className="text-muted"),
                ],
                className="mb-5"
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                dcc.Graph(figure=fig_sankey, config={"displayModeBar": False})
                            ],
                            className="glass-card mb-4"
                        ),
                        width=12
                    )
                ]
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Skill Coverage Comparison Matrix", className="text-white mb-4 fw-semibold"),
                                html.Div(
                                    table_comp,
                                    style={"overflowX": "auto"}
                                )
                            ],
                            className="glass-card"
                        ),
                        width=12
                    )
                ]
            )
        ]
    )
