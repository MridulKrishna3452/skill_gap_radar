import os
import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc
from app.config.settings import settings

# Initialize the Dash application with multi-page support
# Explicitly set the pages_folder location relative to this file
pages_dir = os.path.join(os.path.dirname(__file__), "pages")

app = Dash(
    __name__,
    use_pages=True,
    pages_folder=pages_dir,
    external_stylesheets=[
        dbc.themes.SLATE,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
    ],
    title="Skill Gap Radar AI"
)

# Expose flask server for WSGI/FastAPI integrations
server = app.server

# Custom sidebar layout
def build_sidebar():
    return html.Div(
        [
            html.Div(
                [
                    html.I(className="fa-solid fa-radar fa-2x me-2 text-cyan", style={"color": "#06b6d4"}),
                    html.Span("Radar AI", className="gradient-text fs-3"),
                ],
                className="d-flex align-items-center mb-4 pb-2 border-bottom border-secondary"
            ),
            html.P("Navigation", className="text-uppercase text-secondary fw-bold small mb-3"),
            html.Div(
                [
                    dcc.Link(
                        [
                            html.I(className="fa-solid fa-house me-3"),
                            html.Span("Dashboard Home")
                        ],
                        href="/",
                        className="nav-link-custom active" if page["relative_path"] == "/" else "nav-link-custom",
                        id=f"link-{page['module']}"
                    )
                    for page in dash.page_registry.values()
                ],
                id="sidebar-links-container",
                className="d-flex flex-column"
            ),
            html.Div(
                [
                    html.Hr(className="border-secondary"),
                    html.P("SYSTEM STATUS", className="text-secondary small fw-bold mb-1"),
                    html.Div(
                        [
                            html.Span(className="spinner-grow spinner-grow-sm text-success me-2"),
                            html.Span("Active Pipeline", className="text-muted small")
                        ],
                        className="d-flex align-items-center"
                    )
                ],
                className="mt-auto"
            )
        ],
        className="sidebar d-flex flex-column"
    )

# Master layout
app.layout = dbc.Container(
    [
        dcc.Location(id="url", refresh=False),
        build_sidebar(),
        html.Div(
            dash.page_container,
            className="main-content"
        )
    ],
    fluid=True,
    style={"padding": "0"}
)

# Clientside Callback to handle active navigation class updates
app.clientside_callback(
    """
    function(url) {
        // Find all links in the sidebar
        const links = document.querySelectorAll('#sidebar-links-container a');
        links.forEach(link => {
            const href = link.getAttribute('href');
            // Exact match for root, prefix match for others
            if (url === href || (href !== '/' && url.startsWith(href))) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("sidebar-links-container", "id"),
    dash.Input("url", "pathname")
)

if __name__ == "__main__":
    app.run_server(debug=True, port=settings.DASH_PORT)
