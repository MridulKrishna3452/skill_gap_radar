import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import base64
from app.nlp.resume_analyzer import resume_analyzer

dash.register_page(__name__, path="/resume-analyzer", title="Resume Analyzer - Skill Gap Radar AI")

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
                    html.H2("AI Resume Analyzer", className="gradient-text fw-bold mb-1"),
                    html.P("Upload your PDF resume to assess your skill alignment against industry demands.", className="text-muted"),
                ],
                className="mb-5"
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Analysis Setup", className="text-white mb-4 fw-semibold"),
                                html.Label("Select Your Target Career Goal:", className="text-secondary small fw-bold mb-2"),
                                dcc.Dropdown(
                                    id="resume-target-role",
                                    options=role_options,
                                    value="Data Engineer",
                                    clearable=False,
                                    className="custom-select mb-4"
                                ),
                                html.Label("Upload Resume (PDF):", className="text-secondary small fw-bold mb-2"),
                                dcc.Upload(
                                    id="upload-resume-file",
                                    children=html.Div(
                                        [
                                            html.I(className="fa-solid fa-cloud-arrow-up fa-2x mb-3 text-cyan"),
                                            html.Div("Drag and Drop or Click to Select PDF", className="fw-semibold text-white"),
                                            html.Small("Only PDF files are supported", className="text-secondary mt-1")
                                        ],
                                        className="upload-dragdrop"
                                    ),
                                    multiple=False,
                                    className="mb-4"
                                ),
                                html.Div(id="resume-filename-display", className="text-cyan small mb-3")
                            ],
                            className="glass-card"
                        ),
                        width=12, lg=5, className="mb-4"
                    ),
                    
                    dbc.Col(
                        html.Div(
                            [
                                html.H4("Analysis Report", className="text-white mb-4 fw-semibold"),
                                html.Div(
                                    [
                                        html.I(className="fa-solid fa-file-invoice fa-4x text-secondary mb-3"),
                                        html.Div("Upload a resume to generate an interactive compatibility analysis report.", className="text-muted")
                                    ],
                                    id="resume-results-container",
                                    className="d-flex flex-column align-items-center justify-content-center text-center py-5 h-100"
                                )
                            ],
                            className="glass-card h-100"
                        ),
                        width=12, lg=7, className="mb-4"
                    )
                ]
            )
        ]
    )

# Callback to process upload and analyze resume
@callback(
    Output("resume-filename-display", "children"),
    Output("resume-results-container", "children"),
    Input("upload-resume-file", "contents"),
    State("upload-resume-file", "filename"),
    State("resume-target-role", "value"),
    prevent_initial_call=True
)
def process_resume_upload(contents, filename, target_role):
    if not contents:
        return "", dash.no_update
        
    # Check file type
    if not filename.lower().endswith(".pdf"):
        return f"Error: {filename} is not a PDF", html.Div(
            "Unsupported file type. Please upload a PDF resume.", 
            className="text-danger fw-semibold py-4"
        )
        
    try:
        # Decode base64 contents
        content_type, content_string = contents.split(",")
        decoded_bytes = base64.b64decode(content_string)
        
        # Analyze resume using PDF bytes
        result = resume_analyzer.analyze_resume(decoded_bytes, target_role)
        
        if not result.get("success", False):
            return f"Error reading {filename}", html.Div(
                result.get("error", "Error analyzing resume."),
                className="text-danger fw-semibold py-4"
            )
            
        match_pct = result["match_pct"]
        user_skills = result["user_skills"]
        matched_skills = result["matched_skills"]
        missing_skills = result["missing_skills"]
        recommendations = result["recommendations"]
        
        # Visual color for match percentage
        color_class = "kpi-teal" if match_pct >= 70 else ("kpi-violet" if match_pct >= 40 else "kpi-pink")
        
        # Render lists
        matched_badges = [html.Span(s, className="badge-covered me-2 mb-2 d-inline-block") for s in matched_skills]
        missing_badges = [html.Span(s, className="badge-missing me-2 mb-2 d-inline-block") for s in missing_skills]
        
        # Build learning roadmaps
        roadmap_elements = []
        for rec in recommendations:
            roadmap_steps = [html.Li(step, className="text-muted small mb-1") for step in rec["roadmap"]]
            roadmap_elements.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(rec["skill"], className="fw-bold text-cyan me-3"),
                                html.Small(f"Time: {rec['estimated_time']} | Difficulty: {rec['difficulty']}", className="text-secondary")
                            ],
                            className="d-flex justify-content-between mb-2"
                        ),
                        html.Ol(roadmap_steps, className="ps-3 mb-3")
                    ],
                    className="border-bottom border-secondary mb-3 pb-2"
                )
            )
            
        report_layout = html.Div(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("COMPATIBILITY SCORE", className="text-secondary small fw-bold mb-1"),
                                html.Div(f"{match_pct}%", className=f"kpi-value {color_class} display-4"),
                            ],
                            width=12, md=6, className="text-center text-md-start mb-4"
                        ),
                        dbc.Col(
                            [
                                html.P(f"Target Role: {target_role}", className="text-white fw-bold mb-1"),
                                html.Small(f"Identified {len(user_skills)} technical skills in resume.", className="text-muted")
                            ],
                            width=12, md=6, className="text-center text-md-start mb-4"
                        )
                    ],
                    className="border-bottom border-secondary pb-3 mb-4"
                ),
                
                html.H5("Matched Skills", className="text-white fw-semibold mb-3"),
                html.Div(matched_badges if matched_badges else html.Em("No matching skills found.", className="text-muted"), className="mb-4"),
                
                html.H5("Missing Required Skills", className="text-white fw-semibold mb-3"),
                html.Div(missing_badges if missing_badges else html.Em("No missing skills! You match all requirements.", className="text-muted"), className="mb-4"),
                
                html.H5("Personalized Learning Roadmaps", className="text-white fw-semibold mb-3"),
                html.Div(roadmap_elements if roadmap_elements else html.Em("No learning roadmaps needed.", className="text-muted"))
            ],
            className="text-start"
        )
        
        return f"File uploaded: {filename}", report_layout
        
    except Exception as e:
        return f"Error reading {filename}", html.Div(
            f"Failed to analyze PDF file: {e}",
            className="text-danger fw-semibold py-4"
        )
