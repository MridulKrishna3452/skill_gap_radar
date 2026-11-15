import pandas as pd
from typing import Dict, List, Any
from app.database.connection import db_manager
from app.nlp.pipeline import nlp_pipeline
from app.config.settings import settings
from app.utils.helpers import logger

class GapAnalysisEngine:
    @staticmethod
    def extract_skills_from_curriculum() -> List[str]:
        """Extract standardized skills from all curriculum topics in the DB using NLP pipeline."""
        df_curr = db_manager.get_curriculum_df()
        if df_curr.empty:
            return []
            
        # Combine subject titles, unit titles, and topics
        full_curriculum_text = " ".join(
            (df_curr["subject"].fillna("") + " " + 
             df_curr["unit"].fillna("") + " " + 
             df_curr["topic"].fillna("").astype(str))
        )
        
        # Run NLP pipeline to extract skills
        extracted = nlp_pipeline.extract_skills(full_curriculum_text)
        # Return unique skill names
        return list(set([name for name, conf in extracted]))

    def compute_gap_analysis(self) -> Dict[str, Any]:
        """Compare industry demands against university curriculum to compute gap metrics."""
        logger.info("Computing skill gap analysis...")
        
        # Get industry skills (from jobs and aggregated skills table)
        df_skills = db_manager.get_skills_df()
        df_jobs = db_manager.get_jobs_df()
        
        # Extract skills taught in curriculum
        taught_skills = self.extract_skills_from_curriculum()
        taught_skills_set = set(t.lower() for t in taught_skills)
        
        # Fallback if no jobs or skills yet
        if df_skills.empty:
            # Seed standard mock skills data
            return {
                "coverage_pct": 0.0,
                "gap_score": 100.0,
                "missing_skills": settings.TARGET_SKILLS,
                "covered_skills": [],
                "skills_comparison": pd.DataFrame()
            }
            
        total_jobs = max(len(df_jobs), 1)
        
        comparison_data = []
        for _, row in df_skills.iterrows():
            name = row["name"]
            freq = row["frequency"]
            
            # Demand weight = % of jobs requiring this skill
            demand_weight = freq / total_jobs
            
            # Check coverage
            is_covered = name.lower() in taught_skills_set
            
            # Gap score: Demand weight * (1 - Coverage) * 100
            # Higher gap score = high demand, not covered in syllabus
            gap_score = demand_weight * (1.0 - float(is_covered)) * 100
            
            comparison_data.append({
                "skill": name,
                "industry_frequency": freq,
                "demand_pct": round(demand_weight * 100, 2),
                "is_covered": is_covered,
                "gap_score": round(gap_score, 2),
                "category": row.get("category", "Technology")
            })
            
        df_comp = pd.DataFrame(comparison_data)
        
        # Sort by gap score and industry frequency
        if not df_comp.empty:
            df_comp = df_comp.sort_values(by=["gap_score", "industry_frequency"], ascending=[False, False])
            
        # Calculate coverage % (Out of the top 20 most demanded skills, how many are covered)
        top_skills = df_comp.head(20)
        covered_top = top_skills[top_skills["is_covered"] == True]
        coverage_pct = (len(covered_top) / len(top_skills) * 100) if not top_skills.empty else 0.0
        
        # Identify missing skills (in demand but not covered)
        missing_skills = df_comp[(df_comp["is_covered"] == False) & (df_comp["industry_frequency"] > 0)]["skill"].tolist()
        covered_skills = df_comp[df_comp["is_covered"] == True]["skill"].tolist()
        
        # Calculate overall project gap score (average gap of top 15 skills)
        overall_gap_score = df_comp.head(15)["gap_score"].mean() if not df_comp.empty else 100.0
        
        return {
            "coverage_pct": round(coverage_pct, 2),
            "gap_score": round(overall_gap_score, 2),
            "missing_skills": missing_skills,
            "covered_skills": covered_skills,
            "skills_comparison": df_comp
        }
