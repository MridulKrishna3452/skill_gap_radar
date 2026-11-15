import unittest
import os
import shutil
from pathlib import Path
from app.models.schemas import Job, Curriculum, Skill
from app.database.connection import DatabaseManager
from app.scraper.cleaning import normalize_company, normalize_location, standardize_skills_string, clean_job
from app.nlp.pipeline import NLPPipeline
from app.recommendation.engine import RecommendationEngine

class TestSkillGapRadar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Setup separate test db directory
        cls.test_dir = Path(__file__).parent / "test_data"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.db_path = str(cls.test_dir / "test_radar.db")
        cls.db = DatabaseManager(db_path=cls.db_path)
        cls.nlp = NLPPipeline()
        cls.recs = RecommendationEngine()

    @classmethod
    def tearDownClass(cls):
        # Remove test files and directories
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir)

    def test_database_initialization(self):
        """Verify database tables are created."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Query existing tables in SQLite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        self.assertIn("jobs", tables)
        self.assertIn("curriculum", tables)
        self.assertIn("skills", tables)
        self.assertIn("trends", tables)
        self.assertIn("recommendations", tables)
        conn.close()

    def test_job_cleaning(self):
        """Test the data cleaning utilities."""
        # 1. Normalize company
        self.assertEqual(normalize_company("Google Inc."), "Google")
        self.assertEqual(normalize_company("Hedgehog Private Limited"), "Hedgehog")
        
        # 2. Normalize location
        self.assertEqual(normalize_location("Bangalore Urban"), "Bengaluru")
        self.assertEqual(normalize_location("work from home"), "Remote")
        
        # 3. Standardize skills
        skills_str = "python3, react.js; AWS / docker"
        cleaned_skills = standardize_skills_string(skills_str)
        self.assertIn("Python", cleaned_skills)
        self.assertIn("React", cleaned_skills)
        self.assertIn("AWS", cleaned_skills)
        self.assertIn("Docker", cleaned_skills)

    def test_nlp_extraction(self):
        """Verify SpaCy/Regex matches expected technical terms."""
        text = "We are seeking a senior DevOps specialist who knows Docker, Kubernetes, AWS, and can write Python scripts."
        extracted = self.nlp.extract_skills(text)
        extracted_names = [name for name, conf in extracted]
        
        self.assertIn("Docker", extracted_names)
        self.assertIn("Kubernetes", extracted_names)
        self.assertIn("AWS", extracted_names)
        self.assertIn("Python", extracted_names)
        self.assertIn("DevOps", extracted_names)

    def test_recommendation_engine(self):
        """Check if recommendation roadmaps are generated for valid career roles."""
        # Query DevOps recommendations
        recs = self.recs.generate_recommendations_for_role("DevOps Engineer")
        
        # Since DB is empty, DevOps target requirements (Docker, Kubernetes, AWS, etc.) should be missing
        self.assertTrue(len(recs) > 0)
        
        skills_recomeded = [r.missing_skill for r in recs]
        self.assertIn("Docker", skills_recomeded)
        self.assertIn("Kubernetes", skills_recomeded)

if __name__ == "__main__":
    unittest.main()
