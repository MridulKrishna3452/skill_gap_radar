import sqlite3
import pandas as pd
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config.settings import settings
from app.utils.helpers import logger
from app.models.schemas import Job, Curriculum, Skill, Trend, Recommendation, University

class DatabaseManager:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        """Create and return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize the database and create tables if they do not exist."""
        logger.info(f"Initializing database at: {self.db_path}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create Jobs table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company TEXT,
                location TEXT,
                experience TEXT,
                description TEXT,
                skills_raw TEXT,
                source TEXT,
                date_posted TEXT,
                url TEXT,
                salary TEXT,
                employment_type TEXT,
                category TEXT,
                cleaned_description TEXT,
                extracted_skills TEXT, -- JSON array of strings
                inserted_at TEXT
            )
            """)

            # Create Curriculum table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS curriculum (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                university TEXT,
                course TEXT,
                subject TEXT,
                unit TEXT,
                topic TEXT,
                learning_outcomes TEXT,
                inserted_at TEXT
            )
            """)

            # Create Skills table (Aggregated Industry Skills)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                frequency INTEGER DEFAULT 0,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                category TEXT
            )
            """)

            # Create Trend table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT,
                period TEXT, -- YYYY-MM or YYYY-Www
                frequency INTEGER,
                growth_rate REAL,
                UNIQUE(skill_name, period)
            )
            """)

            # Create Recommendations table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                career_goal TEXT,
                missing_skill TEXT,
                priority TEXT,
                difficulty TEXT,
                estimated_learning_time TEXT,
                learning_roadmap TEXT, -- JSON list of strings
                UNIQUE(career_goal, missing_skill)
            )
            """)

            # Create Universities table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS universities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                location TEXT,
                syllabus_parsed_date TEXT
            )
            """)

            # Create Users table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                target_role TEXT,
                current_skills TEXT -- Comma separated
            )
            """)
            
            conn.commit()
            logger.info("Database schema initialized successfully.")

    # --- Job Insertion and Query ---
    def insert_jobs(self, jobs: List[Job]) -> int:
        """Insert unique jobs into database. Skip duplicate listings based on title, company, description."""
        inserted_count = 0
        now_str = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for job in jobs:
                # Check for duplicates
                cursor.execute(
                    "SELECT id FROM jobs WHERE title = ? AND company = ? AND (description = ? OR url = ?)",
                    (job.title, job.company, job.description, job.url)
                )
                if cursor.fetchone():
                    continue
                
                cursor.execute("""
                INSERT INTO jobs (
                    title, company, location, experience, description, skills_raw, 
                    source, date_posted, url, salary, employment_type, category, 
                    cleaned_description, extracted_skills, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.title, job.company, job.location, job.experience, job.description, 
                    job.skills_raw, job.source, job.date_posted, job.url, job.salary, 
                    job.employment_type, job.category, "", json.dumps([]), now_str
                ))
                inserted_count += 1
            conn.commit()
        logger.info(f"Successfully inserted {inserted_count} new jobs.")
        return inserted_count

    def update_job_extracted_skills(self, job_id: int, cleaned_desc: str, skills: List[str]):
        """Update job with cleaned description and extracted skills."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET cleaned_description = ?, extracted_skills = ? WHERE id = ?",
                (cleaned_desc, json.dumps(skills), job_id)
            )
            conn.commit()

    def get_jobs_df(self) -> pd.DataFrame:
        """Get all jobs as a pandas DataFrame."""
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM jobs", conn)

    # --- Curriculum Insertion and Query ---
    def insert_curriculum_items(self, items: List[Curriculum]) -> int:
        """Insert syllabus curriculum items."""
        inserted_count = 0
        now_str = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for item in items:
                cursor.execute("""
                INSERT INTO curriculum (university, course, subject, unit, topic, learning_outcomes, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (item.university, item.course, item.subject, item.unit, item.topic, item.learning_outcomes, now_str))
                inserted_count += 1
            conn.commit()
        logger.info(f"Inserted {inserted_count} curriculum items.")
        return inserted_count

    def get_curriculum_df(self) -> pd.DataFrame:
        """Get all curriculum data as a DataFrame."""
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM curriculum", conn)

    # --- Skills Insertion and Query ---
    def upsert_aggregated_skills(self, skills: List[Skill]):
        """Upsert aggregated industry skills with combined frequency."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for skill in skills:
                cursor.execute("""
                INSERT INTO skills (name, frequency, confidence, source, category)
                VALUES (?, ?, ?, ?, '')
                ON CONFLICT(name) DO UPDATE SET 
                    frequency = frequency + excluded.frequency,
                    confidence = (confidence + excluded.confidence) / 2.0
                """, (skill.name, skill.frequency, skill.confidence, skill.source))
            conn.commit()

    def get_skills_df(self) -> pd.DataFrame:
        """Get all skills as a DataFrame."""
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM skills ORDER BY frequency DESC", conn)

    # --- Trends ---
    def insert_trends(self, trends: List[Trend]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for trend in trends:
                cursor.execute("""
                INSERT INTO trends (skill_name, period, frequency, growth_rate)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(skill_name, period) DO UPDATE SET 
                    frequency = excluded.frequency,
                    growth_rate = excluded.growth_rate
                """, (trend.skill_name, trend.period, trend.frequency, trend.growth_rate))
            conn.commit()

    def get_trends_df(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM trends", conn)

    # --- Recommendations ---
    def insert_recommendations(self, recs: List[Recommendation]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for rec in recs:
                cursor.execute("""
                INSERT INTO recommendations (career_goal, missing_skill, priority, difficulty, estimated_learning_time, learning_roadmap)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(career_goal, missing_skill) DO UPDATE SET 
                    priority = excluded.priority,
                    difficulty = excluded.difficulty,
                    estimated_learning_time = excluded.estimated_learning_time,
                    learning_roadmap = excluded.learning_roadmap
                """, (rec.career_goal, rec.missing_skill, rec.priority, rec.difficulty, rec.estimated_learning_time, json.dumps(rec.learning_roadmap)))
            conn.commit()

    def get_recommendations_df(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM recommendations", conn)

    # --- Universities ---
    def insert_university(self, uni: University):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO universities (name, location, syllabus_parsed_date)
            VALUES (?, ?, ?)
            """, (uni.name, uni.location, uni.syllabus_parsed_date))
            conn.commit()

    def get_universities_df(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM universities", conn)

# Global singleton connection manager
db_manager = DatabaseManager()
