# Skill Gap Radar AI 🎯📡

**Skill Gap Radar AI** is an advanced, production-quality data engineering and analytics platform that identifies the discrepancy between industry technical requirements and university computer science curricula. 

The platform continuously scrapes job postings across multiple job engines, extracts required skills using a custom NLP pipeline, parses university syllabus PDFs, computes overall gap scores, and visualizes the results on an interactive glassmorphic dark-themed dashboard. It also features an AI-driven resume analyzer and course recommendation engine.

---

## 🏗️ Architecture

```
                      +-------------------+
                      |   Job Postings    |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   Scrapers (API / |
                      |   BS4 / Loaders)  |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |  SQLite Database  | <---+ Ingests Curriculum PDF
                      +---------+---------+     | (Subjects, Units, Topics)
                                |               |
                                v               |
                      +-------------------+     |
                      |   NLP Extraction  | ----+
                      |   (SpaCy/Regex)   |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |    Gap Engine     |
                      +---------+---------+
                                |
                                v
            +-------------------+-------------------+
            |                                       |
            v                                       v
+-----------------------+               +-----------------------+
| Plotly Dash Dashboard |               |  FastAPI Backend REST  |
|      (Port 8050)      |               |      (Port 8000)      |
+-----------------------+               +-----------------------+
```

---

## 🚀 Key Features

- **Multi-Source Job Scrapers**: Built-in support for scraping job listings from Naukri, Internshala, and custom company pages, with robust mock data generation fallbacks if blocked by anti-bot measures (e.g. Cloudflare).
- **Format Ingestion Loaders**: Standardized CSV and JSON loaders to instantly ingest raw datasets.
- **NLP Skill Parsing**: A hybrid SpaCy and PhraseMatcher pipeline that identifies 30+ core industry technologies and calculates confidence ratings based on context.
- **Syllabus PDF Extractor**: Automatically parses subjects, units, topics, and learning outcomes from academic curriculum PDFs using PyMuPDF.
- **Dynamic Gap Analytics**: Computes real-time syllabus coverage percentages, overall gap scores, and identifies top missing skills.
- **Career Roadmaps**: Dynamically recommends learning paths, time estimates, and difficulty scores for 5 roles: Data, AI, DevOps, Cloud, and Software Engineers.
- **Resume Matcher**: Allows uploading a PDF resume, parses its technical skills using NLP, calculates an alignment match score, and outputs personalized roadmaps.
- **Premium Glassmorphic UI**: Beautiful Dash Bootstrap Dark Mode theme styled with Outfit typography, glowing stat cards, Sankey flows, and time-series demand charts.
- **FastAPI REST Endpoints**: Comprehensive endpoints exposing jobs, skills, curriculum, gaps, and resume parsing.

---

## 🛠️ Technology Stack

- **Backend / Core**: Python 3.12, FastAPI, SQLite3
- **Data Engineering / Extraction**: PyMuPDF, Scrapy, BeautifulSoup, Requests, Pandas, NumPy
- **NLP Pipeline**: SpaCy (en_core_web_sm), Regex Phrase Matching
- **Dashboard / Frontend**: Plotly Dash, Plotly Express, Dash Bootstrap Components (DBC), WordCloud, Matplotlib
- **Containerization**: Docker, Docker Compose

---

## 📦 Getting Started

### Local Setup

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd Skill_Gap_Radar_AI
   ```

2. **Create and Activate a Virtual Environment**:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Project in One Go**:
   ```bash
   python run.py
   ```
   *This command will automatically initialize the database schema, run the ingestion and NLP pipelines, generate sample data and syllabus PDFs, and start the API and dashboard.*

5. **Access the Servers**:
   - **Interactive Dashboard**: [http://127.0.0.1:8050](http://127.0.0.1:8050)
   - **FastAPI Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🐳 Docker Deployment

To spin up the entire application stack in a self-contained container with SQLite persistence, run:

```bash
docker compose up --build
```

- Dash Dashboard will be exposed on port `8050`
- FastAPI REST API will be exposed on port `8000`

---

## 🧪 Verification

To run the unit test suite and verify database schema, cleaning pipelines, and NLP matching, execute:

```bash
python -m unittest tests/test_modules.py
```

---

## 📄 API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/jobs` | `GET` | Retrieve list of all scraped job postings |
| `/skills` | `GET` | Retrieve list of industry skills sorted by demand frequency |
| `/curriculum` | `GET` | Retrieve parsed academic curriculum subjects & topics |
| `/gap` | `GET` | Get overall gap metrics (coverage, gap score, comparison matrix) |
| `/recommendations` | `GET` | Get learning roadmaps by target career goal (e.g. `?goal=AI Engineer`) |
| `/resume` | `POST` | Upload PDF resume and get match score + roadmaps |

---

## 🛡️ License

This project is open-source and licensed under the MIT License.
