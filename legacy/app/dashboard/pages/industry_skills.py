import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import io
import base64
from wordcloud import WordCloud
from app.database.connection import db_manager

dash.register_page(__name__, path="/industry-skills", title="Industry Skills - Skill Gap Radar AI")

def generate_wordcloud_base64(skill_freqs: dict) -> str:
    """Generate WordCloud image as base64 string."""
    if not skill_freqs:
        return ""
    try:
        wordcloud = WordCloud(
            width=800, height=400,
            background_color='#0b0f1e',
            colormap='cyan',
            font_path=None  # Standard system font
        ).generate_from_frequencies(skill_freqs)
        
        img = io.BytesIO()
        wordcloud.to_image().save(img, format='PNG')
        img.seek(0)
        return "data:image/png;base64," + base64.b64encode(img.getvalue()).decode()
    except Exception:
        return ""

def layout():
    df_skills = db_manager.get_skills_df()
    df_jobs = db_manager.get_jobs_df()
    
    if df_skills.empty:
        return html.Div([html.H3("No skills data loaded. Run the scrapers or load sample data.", className="text-danger")])

    # Bar chart: Top 15 Industry Skills
    fig_bar = px.bar(
        df_skills.head(15),
        x="frequency",
        y="name",
        orientation="h",
        color="frequency",
        color_continuous_scale="tealgrn",
        labels={"frequency": "Postings Count", "name": "Skill Name"},
        title="Top 15 Demanded Industry Skills"
    )
    fig_bar.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', family='Outfit'),
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
        margin=dict(t=40, b=20, l=100, r=20)
    )

    # Pie chart: Job Categories distribution
    cat_counts = df_jobs["category"].value_counts().reset_index(name="count")
    fig_pie = px.pie(
        cat_counts,
        values="count",
        names="category",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Pastel,
        title="Job Market Distribution by Role"
    )
    fig_pie.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', family='Outfit'),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        margin=dict(t=40, b=80, l=20, r=20)
    )

    # Wordcloud
    skill_freq_dict = dict(zip(df_skills["name"], df_skills["frequency"]))
    wc_src = generate_wordcloud_base64(skill_freq_dict)

    # Job list table
    job_rows = []
    for _, row in df_jobs.head(50).iterrows():
        job_rows.append(
            html.Tr([
                html.Td(row["title"], className="fw-semibold text-white"),
                html.Td(row["company"]),
                html.Td(row["location"]),
                html.Td(row["experience"]),
                html.Td(row["skills_raw"], style={"maxWidth": "250px", "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                html.Td(row["source"])
            ])
        )

    table_jobs = html.Table(
        [
            html.Thead(
                html.Tr([
                    html.Th("Job Title"),
                    html.Th("Company"),
                    html.Th("Location"),
                    html.Th("Experience"),
                    html.Th("Skills Required"),
                    html.Th("Source")
                ])
            ),
            html.Tbody(job_rows)
        ],
        className="custom-table"
    )

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Industry Skills Analysis", className="gradient-text fw-bold mb-1"),
                    html.P("Real-time technical requirements extracted from active job listings.", className="text-muted"),
                ],
                className="mb-5"
            ),
            
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                dcc.Graph(figure=fig_bar, config={"displayModeBar": False})
                            ],
                            className="glass-card mb-4"
                        ),
                        width=12, lg=8
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                dcc.Graph(figure=fig_pie, config={"displayModeBar": False})
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
                                html.H4("Skills Word Cloud", className="text-white mb-4 fw-semibold"),
                                html.Div(
                                    html.Img(src=wc_src, className="img-fluid rounded-3", style={"width": "100%", "maxHeight": "380px"}) if wc_src else "Failed to load word cloud",
                                    className="d-flex justify-content-center align-items-center"
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
                            [
                                html.Div(
                                    [
                                        html.H4("Ingested Job Listings", className="text-white fw-semibold mb-0"),
                                        dbc.Button(
                                            [html.I(className="fa-solid fa-download me-2"), "Export CSV"],
                                            id="btn-export-jobs",
                                            className="btn-export"
                                        ),
                                        dcc.Download(id="download-jobs-csv")
                                    ],
                                    className="d-flex justify-content-between align-items-center mb-4"
                                ),
                                html.Div(
                                    table_jobs,
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

# Callback to handle jobs data export
@callback(
    Output("download-jobs-csv", "data"),
    Input("btn-export-jobs", "n_clicks"),
    prevent_initial_call=True
)
def export_jobs_csv(n_clicks):
    if n_clicks:
        df_jobs = db_manager.get_jobs_df()
        # Remove description and extra JSON columns for clean export
        clean_df = df_jobs.drop(columns=["description", "cleaned_description", "extracted_skills", "inserted_at"], errors="ignore")
        return dcc.send_data_frame(clean_df.to_csv, "jobs_listings.csv", index=False)
