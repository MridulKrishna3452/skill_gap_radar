import fitz  # PyMuPDF
from typing import Dict, Any, List
from app.nlp.pipeline import nlp_pipeline
from app.recommendation.engine import rec_engine
from app.utils.helpers import logger

class ResumeAnalyzer:
    def __init__(self):
        self.nlp = nlp_pipeline
        self.recs = rec_engine

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract all text from a PDF file provided as bytes."""
        text = ""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
        except Exception as e:
            logger.error(f"Error parsing uploaded resume PDF bytes: {e}")
        return text

    def analyze_resume(self, pdf_bytes: bytes, target_role: str) -> Dict[str, Any]:
        """Parse resume, find skills, match against target role, compute match % and recommendations."""
        text = self.extract_text_from_pdf(pdf_bytes)
        
        # If text extraction returns nothing, return default empty response
        if not text.strip():
            return {
                "success": False,
                "error": "Could not extract text from the uploaded resume. Please verify the file is not corrupted or scanned as image.",
                "match_pct": 0,
                "user_skills": [],
                "missing_skills": [],
                "recommendations": []
            }
            
        # Extract skills from resume text
        extracted_skills_tuples = self.nlp.extract_skills(text)
        user_skills = list(set([name for name, conf in extracted_skills_tuples]))
        user_skills_lower = set(s.lower() for s in user_skills)
        
        # Target role requirements
        target_skills = self.recs.role_requirements.get(target_role, [])
        if not target_skills:
            return {
                "success": False,
                "error": f"Target role '{target_role}' is not supported.",
                "match_pct": 0,
                "user_skills": user_skills,
                "missing_skills": [],
                "recommendations": []
            }
            
        # Match calculation
        matched_skills = []
        missing_skills = []
        
        for t_skill in target_skills:
            # Check if user has this skill (matching by target list variations)
            has_skill = False
            variations = self.nlp.skill_variations.get(t_skill, [t_skill])
            for var in variations:
                if var.lower() in user_skills_lower or t_skill.lower() in user_skills_lower:
                    has_skill = True
                    break
                    
            if has_skill:
                matched_skills.append(t_skill)
            else:
                missing_skills.append(t_skill)
                
        # Match %
        total_required = len(target_skills)
        match_pct = round((len(matched_skills) / total_required) * 100) if total_required > 0 else 0
        
        # Build recommendations with roadmaps for missing skills
        recommendations = []
        for m_skill in missing_skills:
            details = self.recs.skill_learning_details.get(m_skill, {
                "difficulty": "Intermediate",
                "time": "3 weeks",
                "roadmap": ["Fundamentals", "Usage in Projects", "Advanced Concepts"]
            })
            recommendations.append({
                "skill": m_skill,
                "priority": "High" if m_skill in ["Python", "SQL", "Docker", "AWS", "Git"] else "Medium",
                "difficulty": details["difficulty"],
                "estimated_time": details["time"],
                "roadmap": details["roadmap"]
            })
            
        return {
            "success": True,
            "match_pct": match_pct,
            "user_skills": user_skills,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "recommendations": recommendations
        }

# Global singleton
resume_analyzer = ResumeAnalyzer()
