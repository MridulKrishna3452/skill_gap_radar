import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
from app.recommendation.engine import rec_engine

dash.register_page(__name__, path="/recommendations", title="Learning Roadmaps - Skill Gap Radar AI")

def layout():
    role_options = [
        {"label": "Data Engineer", "value": "Data Engineer"},
        {"label": "AI Engineer", "value": "AI Engineer"},
        {"label": "DevOps Engineer", "value": "DevOps Engineer"},
        {"label": "Cloud Engineer", "value": "Cloud Engineer"},
        {"label": "Software Engineer", "value": "Software Engineer"}
    ]

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Dynamic Learning Roadmaps", className="gradient-text fw-bold mb-1"),
                    html.P("Recommended roadmaps to bridge gaps between university syllabus and industry demands.", className="text-muted"),
                ],
                className="mb-5"
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Select Your Target Career Goal", className="text-white mb-4 fw-semibold"),
                                html.P("The system will query parsed academic course topics and compare them with job requirements to highlight missing skills.", className="text-muted mb-4"),
                                dcc.Dropdown(
                                    id="recs-target-role",
                                    options=role_options,
                                    value="Data Engineer",
                                    clearable=False,
                                    className="custom-select"
                                )
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
                            id="recommendations-results-container",
                            className="glass-card"
                        ),
                        width=12
                    )
                ]
            )
        ]
    )

# Callback to update recommendations layout based on role
@callback(
    Output("recommendations-results-container", "children"),
    Input("recs-target-role", "value")
)
def update_recommendations_for_role(target_role):
    # Query engine for recommendations based on role
    recs = rec_engine.generate_recommendations_for_role(target_role)
    
    if not recs:
        return html.Div(
            [
                html.I(className="fa-solid fa-circle-check fa-3x text-success mb-3"),
                html.H4("Zero Gaps Detected!", className="text-white fw-bold"),
                html.P(f"The university curriculum fully covers all industry skills required for the {target_role} path.", className="text-muted")
            ],
            className="text-center py-5"
        )
        
    roadmap_cards = []
    for rec in recs:
        # Build checklist / steps
        steps = [html.Li(step, className="text-muted mb-2") for step in rec.learning_roadmap]
        
        priority_color = "bg-danger" if rec.priority == "High" else ("bg-warning text-dark" if rec.priority == "Medium" else "bg-info text-dark")
        difficulty_color = "text-danger" if rec.difficulty == "Advanced" else ("text-warning" if rec.difficulty == "Intermediate" else "text-success")
        
        roadmap_cards.append(
            dbc.Card(
                [
                    dbc.CardHeader(
                        html.Div(
                            [
                                html.H4(rec.missing_skill, className="mb-0 text-cyan fw-bold"),
                                html.Div(
                                    [
                                        html.Span(f"Priority: {rec.priority}", className=f"badge {priority_color} me-2"),
                                        html.Span(f"Time: {rec.estimated_learning_time}", className="badge bg-secondary"),
                                    ]
                                )
                            ],
                            className="d-flex w-100 justify-content-between align-items-center"
                        ),
                        className="bg-transparent border-secondary border-bottom-0 pb-0"
                    ),
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Span("Difficulty: ", className="text-muted small"),
                                    html.Span(rec.difficulty, className=f"small fw-semibold {difficulty_color}")
                                ],
                                className="mb-3"
                            ),
                            html.P("Recommended Roadmap Modules:", className="text-white small fw-bold mb-2"),
                            html.Ol(steps, className="ps-3 mb-0")
                        ]
                    )
                ],
                className="bg-transparent border-secondary mb-4 rounded-3"
            )
        )
        
    layout_content = html.Div(
        [
            html.H4(f"Bridging Gaps for {target_role}", className="text-white mb-4 fw-semibold"),
            html.Div(roadmap_cards)
        ]
    )
    
    return layout_content
