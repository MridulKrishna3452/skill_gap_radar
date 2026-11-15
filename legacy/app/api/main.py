from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import pandas as pd
from app.database.connection import db_manager
from app.analytics.gap_analysis import GapAnalysisEngine
from app.recommendation.engine import rec_engine
from app.nlp.resume_analyzer import resume_analyzer
from app.utils.helpers import logger

app = FastAPI(
    title="Skill Gap Radar AI API",
    description="REST API for industry-academic skill gap analysis and resume compatibility matching.",
    version="1.0.0"
)

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the Skill Gap Radar AI REST API. Access /docs for interactive Swagger API documentation.",
        "status": "online"
    }

@app.get("/jobs", summary="Retrieve all ingested jobs")
def get_jobs(limit: int = 100):
    """Retrieve all jobs ingested by the system (includes title, company, location, source, and raw skills)."""
    try:
        df_jobs = db_manager.get_jobs_df()
        if df_jobs.empty:
            return []
        
        # Limit results and convert to dict
        result = df_jobs.head(limit).to_dict(orient="records")
        return result
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/skills", summary="Get aggregated industry skills demand")
def get_skills():
    """Retrieve list of all extracted industry skills sorted by demand frequency."""
    try:
        df_skills = db_manager.get_skills_df()
        if df_skills.empty:
            return []
        return df_skills.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error fetching skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/curriculum", summary="Get parsed syllabus topics")
def get_curriculum():
    """Retrieve the parsed curriculum subjects, units, topics, and learning outcomes from the database."""
    try:
        df_curr = db_manager.get_curriculum_df()
        if df_curr.empty:
            return []
        return df_curr.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error fetching curriculum: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/gap", summary="Retrieve overall skill gap analysis")
def get_gap_analysis():
    """Run comparison engine and return overall syllabus coverage %, overall gap score, and full skills matrix."""
    try:
        engine = GapAnalysisEngine()
        analysis = engine.compute_gap_analysis()
        
        df_comp = analysis.get("skills_comparison", pd.DataFrame())
        comparison_matrix = df_comp.to_dict(orient="records") if not df_comp.empty else []
        
        return {
            "coverage_percentage": analysis.get("coverage_pct", 0.0),
            "overall_gap_score": analysis.get("gap_score", 100.0),
            "missing_skills": analysis.get("missing_skills", []),
            "covered_skills": analysis.get("covered_skills", []),
            "comparison_matrix": comparison_matrix
        }
    except Exception as e:
        logger.error(f"Error computing gap analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recommendations", summary="Get recommended roadmaps for career goals")
def get_recommendations(goal: str = Query(..., description="Target career role, e.g. 'Data Engineer', 'AI Engineer'")):
    """Get list of missing skills, learning roadmaps, difficulty levels, and time estimates for a selected career goal."""
    if goal not in rec_engine.role_requirements:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid career goal. Select from: {list(rec_engine.role_requirements.keys())}"
        )
    try:
        recs = rec_engine.generate_recommendations_for_role(goal)
        # Convert Pydantic schemas to standard dictionaries for JSON serialization
        return [r.model_dump() for r in recs]
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/resume", summary="Analyze PDF Resume and return match analytics")
async def analyze_resume(
    file: UploadFile = File(..., description="PDF Resume file"), 
    target_role: str = Form(..., description="Career goal role, e.g. 'Data Engineer'")
):
    """Upload a PDF resume, extract technical skills using NLP, calculate role match %, and generate learning paths."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")
        
    if target_role not in rec_engine.role_requirements:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid target role. Select from: {list(rec_engine.role_requirements.keys())}"
        )

    try:
        pdf_bytes = await file.read()
        logger.info(f"Received resume PDF for analysis against target role: {target_role}")
        
        result = resume_analyzer.analyze_resume(pdf_bytes, target_role)
        
        if not result.get("success", False):
            raise HTTPException(status_code=422, detail=result.get("error", "Failed to parse resume text."))
            
        return {
            "match_percentage": result["match_pct"],
            "user_skills_found": result["user_skills"],
            "matched_skills": result["matched_skills"],
            "missing_skills": result["missing_skills"],
            "recommendations": result["recommendations"]
        }
    except Exception as e:
        logger.error(f"Error analyzing resume: {e}")
        raise HTTPException(status_code=500, detail=str(e))
