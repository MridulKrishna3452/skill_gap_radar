import threading
import time
import uvicorn
from app.config.settings import settings
from app.database.connection import db_manager
from app.scraper import InternshalaScraper, NaukriScraper, CareerPagesScraper, CSVJobLoader, JSONJobLoader, clean_job
from app.nlp.pipeline import nlp_pipeline
from app.curriculum.parser import CurriculumParser
from app.analytics.trend_analysis import TrendAnalysisEngine
from app.recommendation.engine import rec_engine
from app.utils.helpers import logger
from app.dashboard.app import app as dash_app

def run_data_pipeline():
    """Execute full ingestion, cleaning, NLP extraction, and syllabus parsing steps on startup."""
    logger.info("================ STARTING DATA ENGINEERING PIPELINE ================")
    
    # 1. Ingest Job listings
    scrapers = [
        InternshalaScraper(),
        NaukriScraper(),
        CareerPagesScraper(),
        CSVJobLoader(),
        JSONJobLoader()
    ]
    
    raw_jobs = []
    for scraper in scrapers:
        try:
            jobs_list = scraper.scrape()
            raw_jobs.extend(jobs_list)
        except Exception as e:
            logger.error(f"Scraper error: {e}")
            
    logger.info(f"Ingested {len(raw_jobs)} total raw jobs. Starting cleaning step...")
    
    # 2. Clean Jobs
    cleaned_jobs = [clean_job(j) for j in raw_jobs]
    db_manager.insert_jobs(cleaned_jobs)
    
    # 3. Perform NLP Skill extraction on jobs
    logger.info("Executing NLP Skill Extraction pipeline on ingested jobs...")
    df_jobs = db_manager.get_jobs_df()
    
    skills_extracted_count = 0
    skills_to_aggregate = []
    
    for _, row in df_jobs.iterrows():
        # Only parse if not already processed
        if not row["extracted_skills"] or row["extracted_skills"] == "[]":
            job_obj = clean_job(row)
            extracted_skills = nlp_pipeline.process_job(job_obj)
            
            # Update individual job in DB with findings
            skill_names = [s.name for s in extracted_skills]
            db_manager.update_job_extracted_skills(row["id"], job_obj.description, skill_names)
            
            skills_to_aggregate.extend(extracted_skills)
            skills_extracted_count += 1
            
    # Aggregated skills update
    if skills_to_aggregate:
        db_manager.upsert_aggregated_skills(skills_to_aggregate)
        
    logger.info(f"Processed NLP skill extraction for {skills_extracted_count} jobs.")
    
    # 4. Generate and Parse Syllabus PDF
    parser = CurriculumParser()
    sample_pdf = parser.create_sample_syllabus_pdf()
    curriculum_count = parser.parse_and_store(sample_pdf, university="National University", course="B.Tech Computer Science")
    logger.info(f"Parsed and stored {curriculum_count} academic curriculum topics from PDF.")
    
    # 5. Populate trends and recommendations
    TrendAnalysisEngine.calculate_and_save_trends()
    rec_engine.seed_recommendations_db()
    
    logger.info("================ PIPELINE COMPLETED SUCCESSFULLY ================")

def run_api_server():
    """Start FastAPI REST API Server."""
    logger.info(f"Starting API Server on http://{settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run("app.api.main:app", host=settings.API_HOST, port=settings.API_PORT, log_level="warning")

def run_dashboard_server():
    """Start Plotly Dash Dashboard Server."""
    logger.info(f"Starting Dashboard Server on http://{settings.API_HOST}:{settings.DASH_PORT}")
    # Disable Dash debug hot-reloader to run smoothly in concurrent threads
    dash_app.run_server(host=settings.API_HOST, port=settings.DASH_PORT, debug=False)

if __name__ == "__main__":
    # 1. Run Data Ingestion and Engineering pipeline first
    run_data_pipeline()
    
    # 2. Boot up servers in parallel threads
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    dash_thread = threading.Thread(target=run_dashboard_server, daemon=True)
    
    api_thread.start()
    dash_thread.start()
    
    logger.info("Servers running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down servers...")
