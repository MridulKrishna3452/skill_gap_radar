import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from collections import Counter
from app.database.connection import db_manager
from app.nlp.pipeline import nlp_pipeline

dash.register_page(__name__, path="/curriculum-skills", title="Academic Curriculum - Skill Gap Radar AI")

def layout():
    df_curr = db_manager.get_curriculum_df()
    df_uni = db_manager.get_universities_df()
    
    if df_curr.empty:
        return html.Div(
            [
                html.H3("No curriculum data parsed. Please run the PDF parser first.", className="text-warning mb-3"),
                html.P("You can parse the sample syllabus PDF automatically by running the main entry script.")
            ],
            className="glass-card"
        )
        
    # Count skills mentioned in curriculum
    skills_found = []
    for _, row in df_curr.iterrows():
        text = str(row["subject"]) + " " + str(row["unit"]) + " " + str(row["topic"]) + " " + str(row["learning_outcomes"])
        extracted = nlp_pipeline.extract_skills(text)
        skills_found.extend([name for name, conf in extracted])
        
    skill_counts = Counter(skills_found)
    df_curr_skills = pd.DataFrame(skill_counts.items(), columns=["Skill", "Mentions"]).sort_values(by="Mentions", ascending=False)
    
    # Bar Chart of Academic Skills Mentions
    fig_curr_bar = px.bar(
        df_curr_skills.head(15),
        x="Mentions",
        y="Skill",
        orientation="h",
        color="Mentions",
        color_continuous_scale="purples",
        labels={"Mentions": "Syllabus Mentions", "Skill": "Skill Name"},
        title="Skills Prevalence in Academic Curriculum"
    )
    fig_curr_bar.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', family='Outfit'),
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
        margin=dict(t=40, b=20, l=100, r=20)
    )

    # University lists layout
    uni_list_items = []
    for _, row in df_uni.iterrows():
        uni_list_items.append(
            dbc.ListGroupItem(
                [
                    html.Div(
                        [
                            html.H5(row["name"], className="mb-1 text-white fw-semibold"),
                            html.Small(row["syllabus_parsed_date"][:10], className="text-secondary"),
                        ],
                        className="d-flex w-100 justify-content-between",
                    ),
                    html.P(f"Location: {row['location']}", className="mb-1 text-muted small"),
                ],
                className="bg-transparent border-secondary py-3"
            )
        )

    # Curriculum database rows
    curr_rows = []
    for _, row in df_curr.iterrows():
        # Quick extract skills in line
        text = str(row["subject"]) + " " + str(row["unit"]) + " " + str(row["topic"])
        in_skills = list(set([name for name, conf in nlp_pipeline.extract_skills(text)]))
        skills_badges = [html.Span(sk, className="badge bg-secondary me-1 my-1") for sk in in_skills]
        
        curr_rows.append(
            html.Tr([
                html.Td(row["subject"], className="fw-semibold text-white"),
                html.Td(row["unit"]),
                html.Td(row["topic"], style={"maxWidth": "350px", "overflow": "hidden", "textOverflow": "ellipsis"}),
                html.Td(skills_badges if skills_badges else html.Em("None", className="text-secondary"))
            ])
        )

    table_curr = html.Table(
        [
            html.Thead(
                html.Tr([
                    html.Th("Subject"),
                    html.Th("Unit/Module"),
                    html.Th("Syllabus Description"),
                    html.Th("Extracted Skills")
                ])
            ),
            html.Tbody(curr_rows)
        ],
        className="custom-table"
    )

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Curriculum Analysis", className="gradient-text fw-bold mb-1"),
                    html.P("Academic syllabus topics parsed and matched with target skills.", className="text-muted"),
                ],
                className="mb-5"
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                dcc.Graph(figure=fig_curr_bar, config={"displayModeBar": False})
                            ],
                            className="glass-card mb-4"
                        ),
                        width=12, lg=8
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Parsed Institutions", className="text-white mb-4 fw-semibold"),
                                dbc.ListGroup(uni_list_items, flush=True)
                            ],
                            className="glass-card mb-4"
                        ),
                        width=12, lg=4
                    )
                ]
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Parsed Syllabus Modules", className="text-white fw-semibold mb-4"),
                                html.Div(
                                    table_curr,
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
